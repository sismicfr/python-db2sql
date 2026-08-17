"""CLI runner — composition root that wires adapters to the use case."""

from __future__ import annotations

import getpass
import signal
import sys
import traceback
from typing import Any, List, Optional, Union

from db2sql import __version__ as db2sql_version
from db2sql.application.use_cases import DumpDatabaseUseCase, MigrateDatabaseUseCase
from db2sql.domain.errors import DomainError
from db2sql.infrastructure.config import (
    AppConfig,
    ConfigError,
    to_dump_request,
    to_migrate_request,
)
from db2sql.infrastructure.logging import ConsoleLogger, init_colorama, Palette
from db2sql.infrastructure.output import ExecutingSink, RotatingFileSink, StreamSink
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.plugins import (
    get_source_reader,
    get_sql_emitter,
    get_target_writer,
    UnknownEmitterError,
    UnknownReaderError,
    UnknownWriterError,
)
from db2sql.infrastructure.writer import TargetWriterError

from .exit_codes import (
    ERROR_ENCOUNTERED,
    ERROR_GENERAL,
    ERROR_INVALID_CONFIGURATION,
    ERROR_UNEXPECTED,
    SUCCESS,
)
from .init_command import run_init
from .parser import (
    AbortExecution,
    build_parser,
    COMMAND_INIT,
    COMMAND_MIGRATE,
    COMMAND_VALIDATE,
    CommandLineError,
)
from .validate_command import run_validate

ExitCode = Union[str, int, None]


class Cli:
    """db2sql command-line front-end."""

    def __init__(self) -> None:
        init_colorama(sys.stdout)
        self._logger: ConsoleLogger = ConsoleLogger()

    @property
    def logger(self) -> ConsoleLogger:
        return self._logger

    def run(self, *args: Any) -> ExitCode:
        try:
            parser = build_parser()
            options = parser.parse_args_with_config(*args)

            if getattr(options, "command", None) == COMMAND_INIT:
                return run_init(options)

            self._logger = ConsoleLogger.from_verbosity(options.verbosity, options.log_file)

            if getattr(options, "command", None) == COMMAND_VALIDATE:
                return run_validate(options, self._logger)

            if options.version:
                self._logger.write_raw(db2sql_version, color=Palette.BRIGHT_GREEN)
                raise AbortExecution(0)

            if options.ask_password:
                password = getpass.getpass("Password:")
                options.config = options.config.model_copy(
                    update={
                        "server": options.config.server.model_copy(update={"password": password})
                    }
                )

            if getattr(options, "command", None) == COMMAND_MIGRATE:
                target_driver = getattr(options, "target_driver", None)
                self._execute_migrate(options.config, target_driver)
                return SUCCESS

            # Either an explicit COMMAND_DUMP or no subcommand at all: dump is
            # the default command, so both land here.
            self._execute(options.config)
        except Exception as exc:
            if not isinstance(exc, AbortExecution):
                self._logger.trace_exception(exc)
            raise exc
        return SUCCESS

    def _execute(self, config: AppConfig) -> None:
        reader = get_source_reader(config.driver, config, self._logger)
        emitter = get_sql_emitter(
            config.target,
            preserve_case=config.dump.preserve_case,
            schema_mapping=dict(config.dump.mapping_schemas),
        )
        request = to_dump_request(config)
        if request.split_size is not None and not request.output_file:
            raise CommandLineError("--split-size requires -f/--file (cannot rotate stdout).")
        with self._open_dump_sink(request) as sink:
            use_case = DumpDatabaseUseCase(
                reader=reader,
                emitter=emitter,
                sink=sink,
                logger=self._logger,
                request=request,
            )
            use_case.execute()

    @staticmethod
    def _open_dump_sink(request: Any) -> Any:
        if request.split_size is not None and request.output_file:
            return RotatingFileSink(request.output_file, request.split_size)
        return StreamSink(request.output_file)

    def _execute_migrate(self, config: AppConfig, target_driver: Optional[str]) -> None:
        """Wire the live migration pipeline: reader → emitter → ExecutingSink → writer."""
        writer_name = target_driver or config.target
        reader = get_source_reader(config.driver, config, self._logger)
        emitter = get_sql_emitter(
            config.target,
            preserve_case=config.dump.preserve_case,
            schema_mapping=dict(config.dump.mapping_schemas),
        )
        writer = get_target_writer(writer_name, config, self._logger)
        request = to_migrate_request(config)
        with writer as live_writer:
            with ExecutingSink(live_writer) as sink:
                use_case = MigrateDatabaseUseCase(
                    reader=reader,
                    emitter=emitter,
                    sink=sink,
                    writer=live_writer,
                    logger=self._logger,
                    request=request,
                )
                use_case.execute()

    def exit_code_from(  # pylint: disable=too-many-return-statements
        self, exception: Optional[BaseException]
    ) -> ExitCode:
        logger = self._logger
        if exception is None:
            return SUCCESS
        if isinstance(exception, AbortExecution):
            return SUCCESS if exception.exitcode == 0 else ERROR_ENCOUNTERED
        if isinstance(exception, CommandLineError):
            logger.error(exception.message)
            return ERROR_UNEXPECTED
        if isinstance(exception, ConfigError):
            logger.error(exception.message)
            return ERROR_INVALID_CONFIGURATION
        if isinstance(exception, (UnknownReaderError, UnknownEmitterError, UnknownWriterError)):
            logger.error(str(exception))
            return ERROR_INVALID_CONFIGURATION
        if isinstance(exception, (SourceReaderError, TargetWriterError, DomainError)):
            logger.error(exception.message)
            return ERROR_GENERAL
        if isinstance(exception, SystemExit):
            if exception.code != 0:
                logger.error(f"Exiting with code: {exception.code}")
            return ERROR_ENCOUNTERED

        logger.error(traceback.format_exc())
        try:
            logger.error(str(exception))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.error(repr(exception))
        return ERROR_UNEXPECTED


def main(args: Optional[List[str]] = None) -> ExitCode:
    def ctrl_c_handler(_signo: Any, _frame: Any) -> None:
        print("You pressed Ctrl+C!")
        sys.exit(2)

    def sigterm_handler(_signo: Any, _frame: Any) -> None:
        print("Received SIGTERM!")
        sys.exit(4)

    def ctrl_break_handler(_signo: Any, _frame: Any) -> None:
        print("You pressed Ctrl+Break!")
        sys.exit(3)

    signal.signal(signal.SIGINT, ctrl_c_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, ctrl_break_handler)  # type: ignore[attr-defined]

    cli = Cli()
    error: ExitCode = SUCCESS
    try:
        result = cli.run(args if args is not None else sys.argv[1:])
        if result is not None and result != SUCCESS:
            error = result
    except BaseException as exc:  # pylint: disable=broad-exception-caught
        error = cli.exit_code_from(exc)
    return error
