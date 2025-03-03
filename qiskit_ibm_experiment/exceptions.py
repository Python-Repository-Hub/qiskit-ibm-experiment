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

"""Exceptions related to the IBM Runtime service."""

from qiskit.exceptions import QiskitError


class IBMError(QiskitError):
    """Base class for errors raised by the runtime service modules."""

    pass


class IBMAccountError(IBMError):
    """Account related errors."""

    pass


class IBMBackendApiProtocolError(IBMError):
    """Errors raised when an unexpected value is received from the server."""

    pass


class IBMInputValueError(IBMError):
    """Error raised due to invalid input value."""

    pass


class IBMNotAuthorizedError(IBMError):
    """Error raised when a service is invoked from an unauthorized account."""

    pass


class IBMApiError(IBMError):
    """Error raised when a server error encountered."""

    pass


class IBMRuntimeError(IBMError):
    """Base class for errors raised by the runtime service modules."""

    pass


class RuntimeDuplicateProgramError(IBMRuntimeError):
    """Error raised when a program being uploaded already exists."""

    pass


class RuntimeProgramNotFound(IBMRuntimeError):
    """Error raised when a program is not found."""

    pass


class RuntimeJobFailureError(IBMRuntimeError):
    """Error raised when a runtime job failed."""

    pass


class RuntimeJobNotFound(IBMRuntimeError):
    """Error raised when a job is not found."""

    pass


class RuntimeInvalidStateError(IBMRuntimeError):
    """Errors raised when the state is not valid for the operation."""

    pass


class IBMExperimentError(IBMError):
    """Base class for errors raised by the experiment service modules."""

    pass


class IBMExperimentEntryNotFound(IBMExperimentError):
    """Errors raised when an experiment entry cannot be found."""


class IBMExperimentEntryExists(IBMExperimentError):
    """Errors raised when an experiment entry already exists."""


class ApiError(IBMError):
    """Generic IBM Quantum API error."""

    pass


class RequestsApiError(ApiError):
    """Exception re-raising a RequestException."""

    def __init__(self, message: str, status_code: int = -1):
        """RequestsApiError constructor.

        Args:
            message: Exception message.
            status_code: Response status code. -1 for unknown status code.
        """
        super().__init__(message)
        self.status_code = status_code


class WebsocketError(ApiError):
    """Exceptions related to websockets."""

    pass


class WebsocketIBMProtocolError(WebsocketError):
    """Exceptions related to IBM Quantum protocol error."""

    pass


class WebsocketAuthenticationError(WebsocketError):
    """Exception caused during websocket authentication."""

    pass


class WebsocketTimeoutError(WebsocketError):
    """Timeout during websocket communication."""

    pass


class WebsocketRetryableError(WebsocketError):
    """A websocket error that can be retried."""

    pass


class AuthenticationLicenseError(ApiError):
    """Exception due to user not having accepted the license agreement."""

    pass


class ApiIBMProtocolError(ApiError):
    """Exception related to IBM Quantum API protocol error."""

    pass


class UserTimeoutExceededError(ApiError):
    """Exceptions related to exceeding user defined timeout."""

    pass
