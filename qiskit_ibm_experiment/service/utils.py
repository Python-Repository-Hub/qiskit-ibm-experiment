# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Utilities for working with IBM Quantum experiments."""

import logging
import os
from typing import Generator, Union, Optional
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import dateutil

from ..exceptions import (
    IBMExperimentEntryNotFound,
    IBMExperimentEntryExists,
    RequestsApiError,
    IBMApiError,
)


@contextmanager
def map_api_error(error_msg: str = "") -> Generator[None, None, None]:
    """Convert an ``RequestsApiError`` to a user facing error."""
    try:
        yield
    except RequestsApiError as api_err:
        if api_err.status_code == 409:
            raise IBMExperimentEntryExists(
                error_msg + f" The server responded with {api_err}"
            ) from None
        if api_err.status_code == 404:
            raise IBMExperimentEntryNotFound(
                error_msg + f" The server responded with {api_err}"
            ) from None
        raise IBMApiError(
            f"Failed to process the request: The server responded with {api_err}"
        ) from None


def setup_logger(logger: logging.Logger) -> None:
    """Setup the logger for the provider modules with the appropriate level.

    It involves:
        * Use the `QISKIT_IBM_PROVIDER_LOG_LEVEL` environment variable to
          determine the log level to use for the provider modules. If an invalid
          level is set, the log level defaults to ``WARNING``. The valid log levels
          are ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, and ``CRITICAL``
          (case-insensitive). If the environment variable is not set, then the parent
          logger's level is used, which also defaults to `WARNING`.
        * Use the `QISKIT_IBM_PROVIDER_LOG_FILE` environment variable to specify the
          filename to use when logging messages. If a log file is specified, the log
          messages will not be logged to the screen. If a log file is not specified,
          the log messages will only be logged to the screen and not to a file.
    """
    log_level = os.getenv("QISKIT_IBM_PROVIDER_LOG_LEVEL", "")
    log_file = os.getenv("QISKIT_IBM_PROVIDER_LOG_FILE", "")

    # Setup the formatter for the log messages.
    log_fmt = "%(module)s.%(funcName)s:%(levelname)s:%(asctime)s: %(message)s"
    formatter = logging.Formatter(log_fmt)

    # Set propagate to `False` since handlers are to be attached.
    logger.propagate = False

    # Log messages to a file (if specified), otherwise log to the screen (default).
    if log_file:
        # Setup the file handler.
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    else:
        # Setup the stream handler, for logging to console, with the given format.
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    # Set the logging level after formatting, if specified.
    if log_level:
        # Default to `WARNING` if the specified level is not valid.
        level = logging.getLevelName(log_level.upper())
        if not isinstance(level, int):
            logger.warning(
                '"%s" is not a valid log level. The valid log levels are: '
                "`DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.",
                log_level,
            )
            level = logging.WARNING
        logger.debug('The logger is being set to level "%s"', level)
        logger.setLevel(level)


# converters


def utc_to_local(utc_dt: Union[datetime, str]) -> datetime:
    """Convert a UTC ``datetime`` object or string to a local timezone ``datetime``.

    Args:
        utc_dt: Input UTC `datetime` or string.

    Returns:
        A ``datetime`` with the local timezone.

    Raises:
        TypeError: If the input parameter value is not valid.
    """
    if isinstance(utc_dt, str):
        utc_dt = dateutil.parser.parse(utc_dt)
    if not isinstance(utc_dt, datetime):
        raise TypeError("Input `utc_dt` is not string or datetime.")
    utc_dt = utc_dt.replace(tzinfo=timezone.utc)  # type: ignore[arg-type]
    local_dt = utc_dt.astimezone(dateutil.tz.tzlocal())  # type: ignore[attr-defined]
    return local_dt


def local_to_utc(local_dt: Union[datetime, str]) -> datetime:
    """Convert a local ``datetime`` object or string to a UTC ``datetime``.

    Args:
        local_dt: Input local ``datetime`` or string.

    Returns:
        A ``datetime`` in UTC.

    Raises:
        TypeError: If the input parameter value is not valid.
    """
    if isinstance(local_dt, str):
        local_dt = dateutil.parser.parse(local_dt)
    if not isinstance(local_dt, datetime):
        raise TypeError("Input `local_dt` is not string or datetime.")

    # Input is considered local if it's ``utcoffset()`` is ``None`` or none-zero.
    if local_dt.utcoffset() is None or local_dt.utcoffset() != timedelta(0):
        local_dt = local_dt.replace(tzinfo=dateutil.tz.tzlocal())
        return local_dt.astimezone(dateutil.tz.UTC)
    return local_dt  # Already in UTC.


def local_to_utc_str(local_dt: Union[datetime, str], suffix: str = "Z") -> str:
    """Convert a local ``datetime`` object or string to a UTC string.

    Args:
        local_dt: Input local ``datetime`` or string.
        suffix: ``Z`` or ``+``, indicating whether the suffix should be ``Z`` or
            ``+00:00``.

    Returns:
        UTC datetime in ISO format.
    """
    utc_dt_str = local_to_utc(local_dt).isoformat()
    if suffix == "Z":
        utc_dt_str = utc_dt_str.replace("+00:00", "Z")
    return utc_dt_str


def str_to_utc(utc_dt: Optional[str]) -> Optional[datetime]:
    """Convert a UTC string to a ``datetime`` object with UTC timezone.

    Args:
        utc_dt: Input UTC string in ISO format.

    Returns:
        A ``datetime`` with the UTC timezone, or ``None`` if the input is ``None``.
    """
    if not utc_dt:
        return None
    parsed_dt = dateutil.parser.isoparse(utc_dt)
    return parsed_dt.replace(tzinfo=timezone.utc)
