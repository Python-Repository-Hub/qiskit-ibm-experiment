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

"""IBM Quantum experiment service."""

import logging
import json
import copy
from typing import Optional, List, Dict, Union, Tuple, Any, Type
from datetime import datetime
from collections import defaultdict
import requests
from .constants import (
    ExperimentShareLevel,
    ResultQuality,
    RESULT_QUALITY_FROM_API,
    RESULT_QUALITY_TO_API,
    DEFAULT_BASE_URL,
)
from .utils import map_api_error, local_to_utc_str, utc_to_local
from .device_component import DeviceComponent
from ..client.experiment import ExperimentClient
from ..exceptions import RequestsApiError, IBMApiError
from ..accounts import AccountManager, Account, ProxyConfiguration

logger = logging.getLogger(__name__)


class IBMExperimentService:
    """Provides experiment related services.

    This class is the main interface to invoke IBM Quantum
    experiment service, which allows you to create, delete, update, query, and
    retrieve experiments, experiment figures, and analysis results.

    .. parsed-literal::
        # Retrieve all experiments.
        experiments = experiment_provider.experiments()

        # Retrieve experiments with filtering.
        experiment_filtered = experiment_provider.experiments(backend_name='ibmq_athens')

        # Retrieve a specific experiment using its ID.
        experiment = experiment_provider.experiment(EXPERIMENT_ID)

        # Upload a new experiment.
        new_experiment_id = .experiment_provider.create_experiment(
            experiment_type="T1",
            backend_name="ibmq_athens",
            metadata={"qubits": 5}
        )

        # Update an experiment.
        experiment_provider.update_experiment(
            experiment_id=EXPERIMENT_ID,
            share_level="Group"
        )

        # Delete an experiment.
        experiment_provider.delete_experiment(EXPERIMENT_ID)

    Similar syntax applies to analysis results and experiment figures.
    """

    _default_preferences = {"auto_save": False}
    _default_options = {"prompt_for_delete": True}
    _DEFAULT_AUTHENTICATION_PREFIX = "/v2/users/loginWithToken"
    _DEFAULT_EXPERIMENT_PREFIX = "/resultsdb"

    def __init__(
        self,
        token: Optional[str] = None,
        url: Optional[str] = None,
        name: Optional[str] = None,
        proxies: Optional[dict] = None,
        verify: Optional[bool] = None,
        local: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """IBMExperimentService constructor.

        Args:
            token: the API token to use when establishing connection with the result DB
            url: the url for the result DB API
        """
        super().__init__()
        if url is None:
            url = DEFAULT_BASE_URL
        self._account = self._discover_account(
            token=token,
            url=url,
            name=name,
            proxies=ProxyConfiguration(**proxies) if proxies else None,
            verify=verify,
            local=local,
        )
        if self._account.preferences is None:
            self._account.preferences = copy.deepcopy(self._default_preferences)
        if not self._account.local:
            db_url = self._account.url + self._DEFAULT_EXPERIMENT_PREFIX
            auth_url = self._account.url + self._DEFAULT_AUTHENTICATION_PREFIX

            self.get_access_token(auth_url)

            self._additional_params = {
                "proxies": self._account.proxies.to_request_params()
                if self._account.proxies is not None
                else None,
                "verify": self._account.verify,
            }
            self._api_client = ExperimentClient(
                self._access_token, db_url, self._additional_params
            )
        self.options = self._default_options
        self.set_option(**kwargs)

    def set_option(self, **kwargs):
        """Sets the options given as keywords"""
        for name, value in kwargs.items():
            if name in self.options:
                self.options[name] = value

    def get_access_token(self, auth_url, api_token=None):
        """Authenticates to the server with the API token, receiving access token
        for the current session"""
        if api_token is None:
            try:
                api_token = self._account.token
            except RuntimeError:
                raise IBMApiError("No API token; cannot connect to service")
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        data = {"apiToken": api_token}
        try:
            response = requests.post(url=auth_url, json=data, headers=headers)
            access_token = response.json()["id"]
        except KeyError:
            raise IBMApiError(
                "Did not receive access token (request returned {})".format(
                    response.json()
                )
            )
        self._access_token = access_token
        return access_token

    @classmethod
    def save_account(
        cls,
        token: Optional[str] = None,
        url: Optional[str] = None,
        name: Optional[str] = None,
        proxies: Optional[dict] = None,
        verify: Optional[bool] = None,
        overwrite: Optional[bool] = False,
    ) -> None:
        """Save the account to disk for future use.

        Args:
            token: IBM Cloud API key or IBM Quantum API token.
            url: The API URL.
                Defaults to https://api.quantum-computing.ibm.com
            name: Name of the account to save.
            proxies: Proxy configuration. Supported optional keys are
                ``urls`` (a dictionary mapping protocol or protocol and host to the URL of the proxy,
                documented at https://docs.python-requests.org/en/latest/api/#requests.Session.proxies),
                ``username_ntlm``, ``password_ntlm`` (username and password to enable NTLM user
                authentication)
            verify: Verify the server's TLS certificate.
            overwrite: ``True`` if the existing account is to be overwritten.
        """
        if url is None:
            url = DEFAULT_BASE_URL
        AccountManager.save(
            token=token,
            url=url,
            name=name,
            proxies=ProxyConfiguration(**proxies) if proxies else None,
            verify=verify,
            overwrite=overwrite,
        )

    def _discover_account(
        self,
        token: Optional[str] = None,
        url: Optional[str] = None,
        name: Optional[str] = None,
        proxies: Optional[ProxyConfiguration] = None,
        verify: Optional[bool] = None,
        local: Optional[bool] = None,
    ) -> Account:
        """Discover account."""
        account = None
        verify_ = verify or True
        if name:
            if any([token, url, local]):
                logger.warning(
                    "Loading account with name %s. Any input 'token', 'url', 'local' are ignored.",
                    name,
                )
            account = AccountManager.get(name=name)
        if local:
            return Account(local=True)

        if token:
            return Account(
                token=token,
                url=url,
                proxies=proxies,
                verify=verify_,
            ).validate()

        if account is None:
            account = AccountManager.get()
        if proxies:
            account.proxies = proxies
        if verify is not None:
            account.verify = verify

        # ensure account is valid, fail early if not
        account.validate()

        return account

    def backends(self) -> List[Dict]:
        """Return a list of backends that can be used for experiments.

        Returns:
            A list of backends.
        """
        return self._api_client.devices()

    def create_experiment(
        self,
        experiment_type: str,
        backend_name: str,
        provider: Any,
        metadata: Optional[Dict] = None,
        experiment_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        share_level: Optional[Union[str, ExperimentShareLevel]] = None,
        start_datetime: Optional[Union[str, datetime]] = None,
        json_encoder: Type[json.JSONEncoder] = json.JSONEncoder,
        **kwargs: Any,
    ) -> str:
        """Create a new experiment in the database.

        Args:
            experiment_type: Experiment type.
            backend_name: Name of the backend the experiment ran on.
            provider: The provider used when running the experiment
            metadata: Experiment metadata.
            experiment_id: Experiment ID. It must be in the ``uuid4`` format.
                One will be generated if not supplied.
            parent_id: The experiment ID of the parent experiment.
                The parent experiment must exist, must be on the same backend as the child,
                and an experiment cannot be its own parent.
            job_ids: IDs of experiment jobs.
            tags: Tags to be associated with the experiment.
            notes: Freeform notes about the experiment.
            share_level: The level at which the experiment is shared. This determines who can
                view the experiment (but not update it). This defaults to "private"
                for new experiments. Possible values include:

                - private: The experiment is only visible to its owner (default)
                - project: The experiment is shared within its project
                - group: The experiment is shared within its group
                - hub: The experiment is shared within its hub
                - public: The experiment is shared publicly regardless of provider
            start_datetime: Timestamp when the experiment started, in local time zone.
            json_encoder: Custom JSON encoder to use to encode the experiment.
            kwargs: Additional experiment attributes that are not supported and will be ignored.

        Returns:
            Experiment ID.

        Raises:
            IBMExperimentEntryExists: If the experiment already exits.
            IBMApiError: If the request to the server failed.
        """
        # pylint: disable=arguments-differ
        if kwargs:
            logger.info(
                "Keywords %s are not supported by IBM Quantum experiment service "
                "and will be ignored.",
                kwargs.keys(),
            )

        data = {
            "type": experiment_type,
            "device_name": backend_name,
            "hub_id": provider.credentials.hub,
            "group_id": provider.credentials.group,
            "project_id": provider.credentials.project,
        }
        data.update(
            self._experiment_data_to_api(
                metadata=metadata,
                experiment_id=experiment_id,
                parent_id=parent_id,
                job_ids=job_ids,
                tags=tags,
                notes=notes,
                share_level=share_level,
                start_dt=start_datetime,
            )
        )

        with map_api_error(f"Experiment {experiment_id} creation failed."):
            response_data = self._api_client.experiment_upload(
                json.dumps(data, cls=json_encoder)
            )
        return response_data["uuid"]

    def update_experiment(
        self,
        experiment_id: str,
        metadata: Optional[Dict] = None,
        job_ids: Optional[List[str]] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        share_level: Optional[Union[str, ExperimentShareLevel]] = None,
        end_datetime: Optional[Union[str, datetime]] = None,
        json_encoder: Type[json.JSONEncoder] = json.JSONEncoder,
        **kwargs: Any,
    ) -> None:
        """Update an existing experiment.

        Args:
            experiment_id: Experiment ID.
            metadata: Experiment metadata.
            job_ids: IDs of experiment jobs.
            notes: Freeform notes about the experiment.
            tags: Tags to be associated with the experiment.
            share_level: The level at which the experiment is shared. This determines who can
                view the experiment (but not update it). This defaults to "private"
                for new experiments. Possible values include:

                - private: The experiment is only visible to its owner (default)
                - project: The experiment is shared within its project
                - group: The experiment is shared within its group
                - hub: The experiment is shared within its hub
                - public: The experiment is shared publicly regardless of provider

            end_datetime: Timestamp for when the experiment ended, in local time.
            json_encoder: Custom JSON encoder to use to encode the experiment.
            kwargs: Additional experiment attributes that are not supported and will be ignored.

        Raises:
            IBMExperimentEntryNotFound: If the experiment does not exist.
            IBMApiError: If the request to the server failed.
        """
        # pylint: disable=arguments-differ
        if kwargs:
            logger.info(
                "Keywords %s are not supported by IBM Quantum experiment service "
                "and will be ignored.",
                kwargs.keys(),
            )

        data = self._experiment_data_to_api(
            metadata=metadata,
            job_ids=job_ids,
            tags=tags,
            notes=notes,
            share_level=share_level,
            end_dt=end_datetime,
        )
        if not data:
            logger.warning("update_experiment() called with nothing to update.")
            return

        with map_api_error(f"Experiment {experiment_id} update failed."):
            self._api_client.experiment_update(
                experiment_id, json.dumps(data, cls=json_encoder)
            )

    def _experiment_data_to_api(
        self,
        metadata: Optional[Dict] = None,
        experiment_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        share_level: Optional[Union[str, ExperimentShareLevel]] = None,
        start_dt: Optional[Union[str, datetime]] = None,
        end_dt: Optional[Union[str, datetime]] = None,
    ) -> Dict:
        """Convert experiment data to API request data.

        Args:
            metadata: Experiment metadata.
            experiment_id: Experiment ID.
            parent_id: Parent experiment ID
            job_ids: IDs of experiment jobs.
            tags: Tags to be associated with the experiment.
            notes: Freeform notes about the experiment.
            share_level: The level at which the experiment is shared.
            start_dt: Experiment start time.
            end_dt: Experiment end time.

        Returns:
            API request data.
        """
        data = {}  # type: Dict[str, Any]
        if metadata:
            data["extra"] = metadata
        if experiment_id:
            data["uuid"] = experiment_id
        if parent_id:
            data["parent_experiment_uuid"] = parent_id
        if share_level:
            if isinstance(share_level, str):
                share_level = ExperimentShareLevel(share_level.lower())
            data["visibility"] = share_level.value
        if tags:
            data["tags"] = tags
        if job_ids:
            data["jobs"] = job_ids
        if notes:
            data["notes"] = notes
        if start_dt:
            data["start_time"] = local_to_utc_str(start_dt)
        if end_dt:
            data["end_time"] = local_to_utc_str(end_dt)
        return data

    def experiment(
        self,
        experiment_id: str,
        json_decoder: Type[json.JSONDecoder] = json.JSONDecoder,
    ) -> Dict:
        """Retrieve a previously stored experiment.

        Args:
            experiment_id: Experiment ID.
            json_decoder: Custom JSON decoder to use to decode the retrieved experiment.

        Returns:
            Retrieved experiment data.

        Raises:
            IBMExperimentEntryNotFound: If the experiment does not exist.
            IBMApiError: If the request to the server failed.
        """
        with map_api_error(f"Experiment {experiment_id} not found."):
            raw_data = self._api_client.experiment_get(experiment_id)
        return self._api_to_experiment_data(json.loads(raw_data, cls=json_decoder))

    def experiments(
        self,
        limit: Optional[int] = 10,
        json_decoder: Type[json.JSONDecoder] = json.JSONDecoder,
        device_components: Optional[List[Union[str, DeviceComponent]]] = None,
        device_components_operator: Optional[str] = None,
        experiment_type: Optional[str] = None,
        experiment_type_operator: Optional[str] = None,
        backend_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tags_operator: Optional[str] = "OR",
        start_datetime_after: Optional[datetime] = None,
        start_datetime_before: Optional[datetime] = None,
        hub: Optional[str] = None,
        group: Optional[str] = None,
        project: Optional[str] = None,
        exclude_public: Optional[bool] = False,
        public_only: Optional[bool] = False,
        exclude_mine: Optional[bool] = False,
        mine_only: Optional[bool] = False,
        parent_id: Optional[str] = None,
        sort_by: Optional[Union[str, List[str]]] = None,
        **filters: Any,
    ) -> List[Dict]:
        """Retrieve all experiments, with optional filtering.

        By default, results returned are as inclusive as possible. For example,
        if you don't specify any filters, all experiments visible to you
        are returned. This includes your own experiments as well as
        those shared with you, from all providers you have access to
        (not just from the provider you used to invoke this experiment service).

        Args:
            limit: Number of experiments to retrieve. ``None`` indicates no limit.
            json_decoder: Custom JSON decoder to use to decode the retrieved experiments.
            device_components: Filter by device components.
            device_components_operator: Operator used when filtering by device components.
                Valid values are ``None`` and "contains":

                    * If ``None``, an analysis result's device components must match
                      exactly for it to be included.
                    * If "contains" is specified, an analysis result's device components
                      must contain at least the values specified by the `device_components`
                      filter.

            experiment_type: Experiment type used for filtering.
            experiment_type_operator: Operator used when filtering by experiment type.
                Valid values are ``None`` and "like":

                * If ``None`` is specified, an experiment's type value must
                  match exactly for it to be included.
                * If "like" is specified, an experiment's type value must
                  contain the value specified by `experiment_type`. For example,
                  ``experiment_type="foo", experiment_type_operator="like"`` will match
                  both ``foo1`` and ``1foo``.
            backend_name: Backend name used for filtering.
            tags: Filter by tags assigned to experiments.
            tags_operator: Logical operator to use when filtering by job tags. Valid
                values are "AND" and "OR":

                    * If "AND" is specified, then an experiment must have all of the tags
                      specified in `tags` to be included.
                    * If "OR" is specified, then an experiment only needs to have any
                      of the tags specified in `tags` to be included.

            start_datetime_after: Filter by the given start timestamp, in local time.
                This is used to find experiments whose start date/time is after
                (greater than or equal to) this local timestamp.
            start_datetime_before: Filter by the given start timestamp, in local time.
                This is used to find experiments whose start date/time is before
                (less than or equal to) this local timestamp.
            hub: Filter by hub.
            group: Filter by hub and group. `hub` must also be specified if `group` is.
            project: Filter by hub, group, and project. `hub` and `group` must also be
                specified if `project` is.
            exclude_public: If ``True``, experiments with ``share_level=public``
                (that is, experiments visible to all users) will not be returned.
                Cannot be ``True`` if `public_only` is ``True``.
            public_only: If ``True``, only experiments with ``share_level=public``
                (that is, experiments visible to all users) will be returned.
                Cannot be ``True`` if `exclude_public` is ``True``.
            exclude_mine: If ``True``, experiments where I am the owner will not be returned.
                Cannot be ``True`` if `mine_only` is ``True``.
            mine_only: If ``True``, only experiments where I am the owner will be returned.
                Cannot be ``True`` if `exclude_mine` is ``True``.
            parent_id: Filter experiments by this parent experiment ID.
            sort_by: Specifies how the output should be sorted. This can be a single sorting
                option or a list of options. Each option should contain a sort key
                and a direction, separated by a semicolon. Valid sort keys are
                "start_datetime" and "experiment_type".
                Valid directions are "asc" for ascending or "desc" for descending.
                For example, ``sort_by=["experiment_type:asc", "start_datetime:desc"]`` will
                return an output list that is first sorted by experiment type in
                ascending order, then by start datetime by descending order.
                By default, experiments are sorted by ``start_datetime``
                descending and ``experiment_id`` ascending.
            **filters: Additional filtering keywords that are not supported and will be ignored.

        Returns:
            A list of experiments. Each experiment is a dictionary containing the
            retrieved experiment data.

        Raises:
            ValueError: If an invalid parameter value is specified.
            IBMApiError: If the request to the server failed.
        """
        # pylint: disable=arguments-differ
        if filters:
            logger.info(
                "Keywords %s are not supported by IBM Quantum experiment service "
                "and will be ignored.",
                filters.keys(),
            )

        if limit is not None and (not isinstance(limit, int) or limit <= 0):  # type: ignore
            raise ValueError(
                f"{limit} is not a valid `limit`, which has to be a positive integer."
            )

        pgh_text = ["project", "group", "hub"]
        pgh_val = [project, group, hub]
        for idx, val in enumerate(pgh_val):
            if val is not None and None in pgh_val[idx + 1 :]:
                raise ValueError(
                    f"If {pgh_text[idx]} is specified, "
                    f"{' and '.join(pgh_text[idx+1:])} must also be specified."
                )

        start_time_filters = []
        if start_datetime_after:
            st_filter = "ge:{}".format(local_to_utc_str(start_datetime_after))
            start_time_filters.append(st_filter)
        if start_datetime_before:
            st_filter = "le:{}".format(local_to_utc_str(start_datetime_before))
            start_time_filters.append(st_filter)

        if exclude_public and public_only:
            raise ValueError("exclude_public and public_only cannot both be True")

        if exclude_mine and mine_only:
            raise ValueError("exclude_mine and mine_only cannot both be True")

        converted = self._filtering_to_api(
            tags=tags,
            tags_operator=tags_operator,
            sort_by=sort_by,
            sort_map={"start_datetime": "start_time", "experiment_type": "type"},
            device_components=device_components,
            device_components_operator=device_components_operator,
            item_type=experiment_type,
            item_type_operator=experiment_type_operator,
        )

        experiments = []
        marker = None
        while limit is None or limit > 0:
            with map_api_error(f"Request failed."):
                response = self._api_client.experiments(
                    limit=limit,
                    marker=marker,
                    backend_name=backend_name,
                    experiment_type=converted["type"],
                    start_time=start_time_filters,
                    device_components=converted["device_components"],
                    tags=converted["tags"],
                    hub=hub,
                    group=group,
                    project=project,
                    exclude_public=exclude_public,
                    public_only=public_only,
                    exclude_mine=exclude_mine,
                    mine_only=mine_only,
                    parent_id=parent_id,
                    sort_by=converted["sort_by"],
                )
            raw_data = json.loads(response, cls=json_decoder)
            marker = raw_data.get("marker")
            for exp in raw_data["experiments"]:
                experiments.append(self._api_to_experiment_data(exp))
            if limit:
                limit -= len(raw_data["experiments"])
            if not marker:  # No more experiments to return.
                break
        return experiments

    def _api_to_experiment_data(
        self,
        raw_data: Dict,
    ) -> Dict:
        """Convert API response to experiment data.

        Args:
            raw_data: API response

        Returns:
            Converted experiment data.
        """
        backend_name = raw_data["device_name"]
        # should decide whether the wanted functionality is returning
        # an actual backend (requires a given provider) or simply the name
        # backend = self._provider.get_backend(backend_name)
        backend = backend_name

        extra_data: Dict[str, Any] = {}
        self._convert_dt(
            raw_data.get("created_at", None), extra_data, "creation_datetime"
        )
        self._convert_dt(raw_data.get("start_time", None), extra_data, "start_datetime")
        self._convert_dt(raw_data.get("end_time", None), extra_data, "end_datetime")
        self._convert_dt(
            raw_data.get("updated_at", None), extra_data, "updated_datetime"
        )

        out_dict = {
            "experiment_type": raw_data["type"],
            "backend": backend,
            "experiment_id": raw_data["uuid"],
            "parent_id": raw_data.get("parent_experiment_uuid", None),
            "tags": raw_data.get("tags", None),
            "job_ids": raw_data["jobs"],
            "share_level": raw_data.get("visibility", None),
            "metadata": raw_data.get("extra", None),
            "figure_names": raw_data.get("plot_names", None),
            "notes": raw_data.get("notes", ""),
            "hub": raw_data.get("hub_id", ""),
            "group": raw_data.get("group_id", ""),
            "project": raw_data.get("project_id", ""),
            "owner": raw_data.get("owner", ""),
            **extra_data,
        }
        return out_dict

    def _convert_dt(
        self, timestamp: Optional[str], data: Dict, field_name: str
    ) -> None:
        """Convert input timestamp.

        Args:
            timestamp: Timestamp to be converted.
            data: Data used to stored the converted timestamp.
            field_name: Name used to store the converted timestamp.
        """
        if not timestamp:
            return
        data[field_name] = utc_to_local(timestamp)

    def delete_experiment(self, experiment_id: str) -> None:
        """Delete an experiment.

        Args:
            experiment_id: Experiment ID.

        Note:
            This method prompts for confirmation and requires a response before proceeding.

        Raises:
            IBMApiError: If the request to the server failed.
        """
        if not self._confirm_delete(
            "Are you sure you want to delete the experiment? "
            "Results and plots for the experiment will also be deleted. [y/N]: "
        ):
            return
        try:
            self._api_client.experiment_delete(experiment_id)
        except RequestsApiError as api_err:
            if api_err.status_code == 404:
                logger.warning("Experiment %s not found.", experiment_id)
            else:
                raise IBMApiError(f"Failed to process the request: {api_err}") from None

    def create_analysis_result(
        self,
        experiment_id: str,
        result_data: Dict,
        result_type: str,
        device_components: Optional[
            Union[List[Union[str, DeviceComponent]], str, DeviceComponent]
        ] = None,
        tags: Optional[List[str]] = None,
        quality: Union[ResultQuality, str] = ResultQuality.UNKNOWN,
        verified: bool = False,
        result_id: Optional[str] = None,
        chisq: Optional[float] = None,
        json_encoder: Type[json.JSONEncoder] = json.JSONEncoder,
        **kwargs: Any,
    ) -> str:
        """Create a new analysis result in the database.

        Args:
            experiment_id: ID of the experiment this result is for.
            result_data: Result data to be stored.
            result_type: Analysis result type.
            device_components: Target device components, such as qubits.
            tags: Tags to be associated with the analysis result.
            quality: Quality of this analysis.
            verified: Whether the result quality has been verified.
            result_id: Analysis result ID. It must be in the ``uuid4`` format.
                One will be generated if not supplied.
            chisq: chi^2 decimal value of the fit.
            json_encoder: Custom JSON encoder to use to encode the analysis result.
            kwargs: Additional analysis result attributes that are not supported
                and will be ignored.

        Returns:
            Analysis result ID.

        Raises:
            IBMExperimentEntryExists: If the analysis result already exits.
            IBMApiError: If the request to the server failed.
        """
        # pylint: disable=arguments-differ
        if kwargs:
            logger.info(
                "Keywords %s are not supported by IBM Quantum experiment service "
                "and will be ignored.",
                kwargs.keys(),
            )

        components = []
        if device_components:
            if not isinstance(device_components, list):
                device_components = [device_components]
            for comp in device_components:
                components.append(str(comp))

        if isinstance(quality, str):
            quality = ResultQuality(quality.upper())

        request = self._analysis_result_to_api(
            experiment_id=experiment_id,
            device_components=components,
            data=result_data,
            result_type=result_type,
            tags=tags,
            quality=quality,
            verified=verified,
            result_id=result_id,
            chisq=chisq,
        )
        with map_api_error(f"Analysis result {result_id} creation failed."):
            response = self._api_client.analysis_result_create(
                json.dumps(request, cls=json_encoder)
            )
        return response["uuid"]

    def update_analysis_result(
        self,
        result_id: str,
        result_data: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
        quality: Union[ResultQuality, str] = None,
        verified: bool = None,
        chisq: Optional[float] = None,
        json_encoder: Type[json.JSONEncoder] = json.JSONEncoder,
        **kwargs: Any,
    ) -> None:
        """Update an existing analysis result.

        Args:
            result_id: Analysis result ID.
            result_data: Result data to be stored.
            quality: Quality of this analysis.
            verified: Whether the result quality has been verified.
            tags: Tags to be associated with the analysis result.
            chisq: chi^2 decimal value of the fit.
            json_encoder: Custom JSON encoder to use to encode the analysis result.
            kwargs: Additional analysis result attributes that are not supported
                and will be ignored.

        Raises:
            IBMExperimentEntryNotFound: If the analysis result does not exist.
            IBMApiError: If the request to the server failed.
        """
        # pylint: disable=arguments-differ
        if kwargs:
            logger.info(
                "Keywords %s are not supported by IBM Quantum experiment service "
                "and will be ignored.",
                kwargs.keys(),
            )

        if isinstance(quality, str):
            quality = ResultQuality(quality.upper())

        request = self._analysis_result_to_api(
            data=result_data, tags=tags, quality=quality, verified=verified, chisq=chisq
        )
        with map_api_error(f"Analysis result {result_id} update failed."):
            self._api_client.analysis_result_update(
                result_id, json.dumps(request, cls=json_encoder)
            )

    def _confirm_delete(self, msg: str) -> bool:
        """Confirms a delete command; if the options indicate a prompt should be
        dislayed, display one and verify the user input"""
        if not self.options["prompt_for_delete"]:
            return True
        confirmation = input("\n" + msg)
        if confirmation not in ("y", "Y"):
            return False
        return True

    def _analysis_result_to_api(
        self,
        experiment_id: Optional[str] = None,
        device_components: Optional[List[str]] = None,
        data: Optional[Dict] = None,
        result_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        quality: Optional[ResultQuality] = None,
        verified: Optional[bool] = None,
        result_id: Optional[str] = None,
        chisq: Optional[float] = None,
    ) -> Dict:
        """Convert analysis result fields to server format.

        Args:
            experiment_id: ID of the experiment this result is for.
            data: Result data to be stored.
            result_type: Analysis result type.
            device_components: Target device components, such as qubits.
            tags: Tags to be associated with the analysis result.
            quality: Quality of this analysis.
            verified: Whether the result quality has been verified.
            result_id: Analysis result ID. It must be in the ``uuid4`` format.
                One will be generated if not supplied.
            chisq: chi^2 decimal value of the fit.

        Returns:
            API request data.
        """
        out = {}  # type: Dict[str, Any]
        if experiment_id:
            out["experiment_uuid"] = experiment_id
        if device_components:
            out["device_components"] = device_components
        if data:
            out["fit"] = data
        if result_type:
            out["type"] = result_type
        if tags:
            out["tags"] = tags
        if quality:
            out["quality"] = RESULT_QUALITY_TO_API[quality]
        if verified is not None:
            out["verified"] = verified
        if result_id:
            out["uuid"] = result_id
        if chisq:
            out["chisq"] = chisq
        return out

    def analysis_result(
        self, result_id: str, json_decoder: Type[json.JSONDecoder] = json.JSONDecoder
    ) -> Dict:
        """Retrieve a previously stored analysis result.

        Args:
            result_id: Analysis result ID.
            json_decoder: Custom JSON decoder to use to decode the retrieved analysis result.

        Returns:
            Retrieved analysis result.

        Raises:
            IBMExperimentEntryNotFound: If the analysis result does not exist.
            IBMApiError: If the request to the server failed.
        """
        with map_api_error(f"Analysis result {result_id} not found."):
            raw_data = self._api_client.analysis_result_get(result_id)

        return self._api_to_analysis_result(json.loads(raw_data, cls=json_decoder))

    def analysis_results(
        self,
        limit: Optional[int] = 10,
        json_decoder: Type[json.JSONDecoder] = json.JSONDecoder,
        device_components: Optional[List[Union[str, DeviceComponent]]] = None,
        device_components_operator: Optional[str] = None,
        experiment_id: Optional[str] = None,
        result_type: Optional[str] = None,
        result_type_operator: Optional[str] = None,
        backend_name: Optional[str] = None,
        quality: Optional[
            Union[List[Union[ResultQuality, str]], ResultQuality, str]
        ] = None,
        verified: Optional[bool] = None,
        tags: Optional[List[str]] = None,
        tags_operator: Optional[str] = "OR",
        creation_datetime_after: Optional[datetime] = None,
        creation_datetime_before: Optional[datetime] = None,
        sort_by: Optional[Union[str, List[str]]] = None,
        **filters: Any,
    ) -> List[Dict]:
        """Retrieve all analysis results, with optional filtering.

        Args:
            limit: Number of analysis results to retrieve.
            json_decoder: Custom JSON decoder to use to decode the retrieved analysis results.
            device_components: Filter by device components.
            device_components_operator: Operator used when filtering by device components.
                Valid values are ``None`` and "contains":

                    * If ``None``, an analysis result's device components must match
                      exactly for it to be included.
                    * If "contains" is specified, an analysis result's device components
                      must contain at least the values specified by the `device_components`
                      filter.

            experiment_id: Experiment ID used for filtering.
            result_type: Analysis result type used for filtering.
            result_type_operator: Operator used when filtering by result type.
                Valid values are ``None`` and "like":

                * If ``None`` is specified, an analysis result's type value must
                  match exactly for it to be included.
                * If "like" is specified, an analysis result's type value must
                  contain the value specified by `result_type`. For example,
                  ``result_type="foo", result_type_operator="like"`` will match
                  both ``foo1`` and ``1foo``.

            backend_name: Backend name used for filtering.
            quality: Quality value used for filtering. If a list is given, analysis results
                whose quality value is in the list will be included.
            verified: Indicates whether this result has been verified..
            tags: Filter by tags assigned to analysis results. This can be used
                with `tags_operator` for granular filtering.
            tags_operator: Logical operator to use when filtering by tags. Valid
                values are "AND" and "OR":

                    * If "AND" is specified, then an analysis result must have all of the tags
                      specified in `tags` to be included.
                    * If "OR" is specified, then an analysis result only needs to have any
                      of the tags specified in `tags` to be included.

            creation_datetime_after: Filter by the given creation timestamp, in local time.
                This is used to find analysis results whose creation date/time is after
                (greater than or equal to) this local timestamp.
            creation_datetime_before: Filter by the given creation timestamp, in local time.
                This is used to find analysis results whose creation date/time is before
                (less than or equal to) this local timestamp.
            sort_by: Specifies how the output should be sorted. This can be a single sorting
                option or a list of options. Each option should contain a sort key
                and a direction. Valid sort keys are "creation_datetime", "device_components",
                and "result_type". Valid directions are "asc" for ascending or "desc" for
                descending.
                For example, ``sort_by=["result_type: asc", "creation_datetime:desc"]`` will
                return an output list that is first sorted by result type in
                ascending order, then by creation datetime by descending order.
                By default, analysis results are sorted by ``creation_datetime``
                descending and ``result_id`` ascending.

            **filters: Additional filtering keywords that are not supported and will be ignored.

        Returns:
            A list of analysis results. Each analysis result is a dictionary
            containing the retrieved analysis result.

        Raises:
            ValueError: If an invalid parameter value is specified.
            IBMApiError: If the request to the server failed.
        """
        # pylint: disable=arguments-differ
        if filters:
            logger.info(
                "Keywords %s are not supported by IBM Quantum experiment service "
                "and will be ignored.",
                filters.keys(),
            )

        if limit is not None and (not isinstance(limit, int) or limit <= 0):  # type: ignore
            raise ValueError(
                f"{limit} is not a valid `limit`, which has to be a positive integer."
            )

        quality = self._quality_filter_to_api(quality)

        created_at_filters = []
        if creation_datetime_after:
            ca_filter = "ge:{}".format(local_to_utc_str(creation_datetime_after))
            created_at_filters.append(ca_filter)
        if creation_datetime_before:
            ca_filter = "le:{}".format(local_to_utc_str(creation_datetime_before))
            created_at_filters.append(ca_filter)

        converted = self._filtering_to_api(
            tags=tags,
            tags_operator=tags_operator,
            sort_by=sort_by,
            sort_map={
                "creation_datetime": "created_at",
                "device_components": "device_components",
                "result_type": "type",
            },
            device_components=device_components,
            device_components_operator=device_components_operator,
            item_type=result_type,
            item_type_operator=result_type_operator,
        )

        results = []
        marker = None
        while limit is None or limit > 0:
            with map_api_error("Request failed."):
                response = self._api_client.analysis_results(
                    limit=limit,
                    marker=marker,
                    backend_name=backend_name,
                    device_components=converted["device_components"],
                    experiment_uuid=experiment_id,
                    result_type=converted["type"],
                    quality=quality,
                    verified=verified,
                    tags=converted["tags"],
                    created_at=created_at_filters,
                    sort_by=converted["sort_by"],
                )
            raw_data = json.loads(response, cls=json_decoder)
            marker = raw_data.get("marker")
            for result in raw_data["analysis_results"]:
                results.append(self._api_to_analysis_result(result))
            if limit:
                limit -= len(raw_data["analysis_results"])
            if not marker:  # No more experiments to return.
                break
        return results

    def _quality_filter_to_api(
        self,
        quality: Optional[
            Union[List[Union[ResultQuality, str]], ResultQuality, str]
        ] = None,
    ) -> Optional[Union[str, List[str]]]:
        """Convert quality filter to server format."""
        if not quality:
            return None
        if not isinstance(quality, list):
            quality = [quality]

        api_quals = []
        for qual in quality:
            if isinstance(qual, str):
                qual = ResultQuality(qual.upper())
            api_qual = RESULT_QUALITY_TO_API[qual]
            if api_qual not in api_quals:
                api_quals.append(api_qual)

        if len(api_quals) == 1:
            return api_quals[0]
        if len(api_quals) == len(ResultQuality):
            return None

        return "in:" + ",".join(api_quals)

    def _filtering_to_api(
        self,
        tags: Optional[List[str]] = None,
        tags_operator: Optional[str] = "OR",
        sort_by: Optional[Union[str, List[str]]] = None,
        sort_map: Optional[Dict] = None,
        device_components: Optional[List[Union[str, DeviceComponent]]] = None,
        device_components_operator: Optional[str] = None,
        item_type: Optional[str] = None,
        item_type_operator: Optional[str] = None,
    ) -> Dict:
        """Convert filtering inputs to server format.

        Args:
            tags: Filtering by tags.
            tags_operator: Tags operator.
            sort_by: Specifies how the output should be sorted.
            sort_map: Sort key to API key mapping.
            device_components: Filter by device components.
            device_components_operator: Device component operator.
            item_type: Item type used for filtering.
            item_type_operator: Operator used when filtering by type.

        Returns:
            A dictionary of mapped filters.

        Raises:
            ValueError: If an input key is invalid.
        """
        tags_filter = None
        if tags:
            if tags_operator.upper() == "OR":
                tags_filter = "any:" + ",".join(tags)
            elif tags_operator.upper() == "AND":
                tags_filter = "contains:" + ",".join(tags)
            else:
                raise ValueError(
                    "{} is not a valid `tags_operator`. Valid values are "
                    '"AND" and "OR".'.format(tags_operator)
                )

        sort_list = []
        if sort_by:
            if not isinstance(sort_by, list):
                sort_by = [sort_by]
            for sorter in sort_by:
                key, direction = sorter.split(":")
                key = key.lower()
                if key not in sort_map:
                    raise ValueError(
                        f'"{key}" is not a valid sort key. '
                        f"Valid sort keys are {sort_map.keys()}"
                    )
                key = sort_map[key]
                if direction not in ["asc", "desc"]:
                    raise ValueError(
                        f'"{direction}" is not a valid sorting direction.'
                        f'Valid directions are "asc" and "desc".'
                    )
                sort_list.append(f"{key}:{direction}")
            sort_by = ",".join(sort_list)

        if device_components:
            device_components = [str(comp) for comp in device_components]
            if device_components_operator:
                if device_components_operator != "contains":
                    raise ValueError(
                        f"{device_components_operator} is not a valid "
                        f"device_components_operator value. Valid values "
                        f'are ``None`` and "contains"'
                    )
                device_components = "contains:" + ",".join(
                    device_components
                )  # type: ignore

        if item_type and item_type_operator:
            if item_type_operator != "like":
                raise ValueError(
                    f'"{item_type_operator}" is not a valid type operator value. '
                    f'Valid values are ``None`` and "like".'
                )
            item_type = "like:" + item_type

        return {
            "tags": tags_filter,
            "sort_by": sort_by,
            "device_components": device_components,
            "type": item_type,
        }

    def _api_to_analysis_result(
        self,
        raw_data: Dict,
    ) -> Dict:
        """Map API response to a dictionary representing an analysis result.

        Args:
            raw_data: API response data.

        Returns:
            Converted analysis result data.
        """
        extra_data = {}

        chisq = raw_data.get("chisq", None)
        if chisq:
            extra_data["chisq"] = chisq

        backend_name = raw_data["device_name"]
        if backend_name:
            extra_data["backend_name"] = backend_name

        quality = raw_data.get("quality", None)
        if quality:
            quality = RESULT_QUALITY_FROM_API[quality]

        self._convert_dt(
            raw_data.get("created_at", None), extra_data, "creation_datetime"
        )
        self._convert_dt(
            raw_data.get("updated_at", None), extra_data, "updated_datetime"
        )

        out_dict = {
            "result_data": raw_data.get("fit", {}),
            "result_type": raw_data.get("type", None),
            "device_components": raw_data.get("device_components", []),
            "experiment_id": raw_data.get("experiment_uuid"),
            "result_id": raw_data.get("uuid", None),
            "quality": quality,
            "verified": raw_data.get("verified", False),
            "tags": raw_data.get("tags", []),
            "service": self,
            **extra_data,
        }
        return out_dict

    def delete_analysis_result(self, result_id: str) -> None:
        """Delete an analysis result.

        Args:
            result_id: Analysis result ID.

        Note:
            This method prompts for confirmation and requires a response before proceeding.

        Raises:
            IBMApiError: If the request to the server failed.
        """
        if not self._confirm_delete(
            "Are you sure you want to delete the analysis result? [y/N]: "
        ):
            return
        try:
            self._api_client.analysis_result_delete(result_id)
        except RequestsApiError as api_err:
            if api_err.status_code == 404:
                logger.warning("Analysis result %s not found.", result_id)
            else:
                raise IBMApiError(f"Failed to process the request: {api_err}") from None

    def create_figure(
        self,
        experiment_id: str,
        figure: Union[str, bytes],
        figure_name: Optional[str] = None,
        sync_upload: bool = True,
    ) -> Tuple[str, int]:
        """Store a new figure in the database.

        Note:
            Currently only SVG figures are supported.

        Args:
            experiment_id: ID of the experiment this figure is for.
            figure: Name of the figure file or figure data to store.
            figure_name: Name of the figure. If ``None``, the figure file name, if
                given, or a generated name is used.
            sync_upload: If ``True``, the plot will be uploaded synchronously.
                Otherwise the upload will be asynchronous.

        Returns:
            A tuple of the name and size of the saved figure.

        Raises:
            IBMExperimentEntryExists: If the figure already exits.
            IBMApiError: If the request to the server failed.
        """
        if figure_name is None:
            if isinstance(figure, str):
                figure_name = figure
            else:
                figure_name = "figure_{}.svg".format(datetime.now().isoformat())

        # currently the resultdb enforces files to end with .svg
        if not figure_name.endswith(".svg"):
            figure_name += ".svg"

        with map_api_error(f"Figure {figure_name} creation failed."):
            response = self._api_client.experiment_plot_upload(
                experiment_id, figure, figure_name, sync_upload=sync_upload
            )
        return response["name"], response["size"]

    def update_figure(
        self,
        experiment_id: str,
        figure: Union[str, bytes],
        figure_name: str,
        sync_upload: bool = True,
    ) -> Tuple[str, int]:
        """Update an existing figure.

        Args:
            experiment_id: Experiment ID.
            figure: Name of the figure file or figure data to store.
            figure_name: Name of the figure.
            sync_upload: If ``True``, the plot will be uploaded synchronously.
                Otherwise the upload will be asynchronous.

        Returns:
            A tuple of the name and size of the saved figure.

        Raises:
            IBMExperimentEntryNotFound: If the figure does not exist.
            IBMApiError: If the request to the server failed.
        """
        with map_api_error(f"Figure {figure_name} update failed."):
            response = self._api_client.experiment_plot_update(
                experiment_id, figure, figure_name, sync_upload=sync_upload
            )

        return response["name"], response["size"]

    def figure(
        self, experiment_id: str, figure_name: str, file_name: Optional[str] = None
    ) -> Union[int, bytes]:
        """Retrieve an existing figure.

        Args:
            experiment_id: Experiment ID.
            figure_name: Name of the figure.
            file_name: Name of the local file to save the figure to. If ``None``,
                the content of the figure is returned instead.

        Returns:
            The size of the figure if `file_name` is specified. Otherwise the
            content of the figure in bytes.

        Raises:
            IBMExperimentEntryNotFound: If the figure does not exist.
            IBMApiError: If the request to the server failed.
        """
        with map_api_error(f"Figure {figure_name} not found."):
            data = self._api_client.experiment_plot_get(experiment_id, figure_name)

        if file_name:
            with open(file_name, "wb") as file:
                num_bytes = file.write(data)
            return num_bytes

        return data

    def delete_figure(self, experiment_id: str, figure_name: str) -> None:
        """Delete an experiment plot.

        Note:
            This method prompts for confirmation and requires a response before proceeding.

        Args:
            experiment_id: Experiment ID.
            figure_name: Name of the figure.

        Raises:
            IBMApiError: If the request to the server failed.
        """
        if not self._confirm_delete(
            "Are you sure you want to delete the experiment plot? [y/N]: "
        ):
            return
        try:
            self._api_client.experiment_plot_delete(experiment_id, figure_name)
        except RequestsApiError as api_err:
            if api_err.status_code == 404:
                logger.warning("Figure %s not found.", figure_name)
            else:
                raise IBMApiError(f"Failed to process the request: {api_err}") from None

    def device_components(
        self, backend_name: Optional[str] = None
    ) -> Union[Dict[str, List], List]:
        """Return the device components.

        Args:
            backend_name: Name of the backend whose components are to be retrieved.

        Returns:
            A list of device components if `backend_name` is specified. Otherwise
            a dictionary whose keys are backend names the values
            are lists of device components for the backends.

        Raises:
            IBMApiError: If the request to the server failed.
        """
        with map_api_error(
            f"Device components call for backend {backend_name} failed."
        ):
            raw_data = self._api_client.device_components(backend_name)

        components = defaultdict(list)
        for data in raw_data:
            components[data["device_name"]].append(data["type"])

        if backend_name:
            return components[backend_name]

        return dict(components)

    def files(self, experiment_id: str) -> str:
        """Retrieve the file list for an experiment

        Args:
            experiment_id: Experiment ID.

        Returns:
            The file list metadata

        Raises:
            IBMExperimentEntryNotFound: If the experiment does not exist.
            IBMApiError: If the request to the server failed.
        """
        with map_api_error(f"Experiment {experiment_id} file list not received."):
            data = self._api_client.experiment_files_get(experiment_id)
        return data

    def file_upload(
        self, experiment_id: str, file_name: str, file_data: Union[Dict, str]
    ):
        """Uploads a data file to the DB

        Args:
            experiment_id: The experiment the data file belongs to
            file_name: The expected filename of the data file
            file_data: The dictionary of data to save, or JSON serialization of it

        Additional info:
            The filename is expected to end with ".json" (otherwise it will be added)
            and the data itself should be either a dictionary or a JSON serialization
            with the default encoder.
        """
        # currently the resultdb enforces files to end with .json or .yaml
        if not file_name.endswith(".json"):
            file_name += ".json"
        if isinstance(file_data, Dict):
            file_data = json.dumps(file_data)
        self._api_client.experiment_file_upload(experiment_id, file_name, file_data)

    def file_download(self, experiment_id: str, file_name: str) -> Dict:
        """Downloads a data file from the DB and returns its deserialization
        Args:
            experiment_id: The experiment the data file belongs to
            file_name: The filename of the data file
        Returns:
            The JSON deserialization of the data file
        Additional info:
            The filename is expected to end with ".json", otherwise
            it will be added.
        """
        if not file_name.endswith(".json"):
            file_name += ".json"
        file_data = self._api_client.experiment_file_download(experiment_id, file_name)
        return file_data

    @property
    def preferences(self) -> Dict:
        """Return saved experiment preferences.

        Note:
            These are preferences passed to the applications that use this service
            and have no effect on the service itself. It is up to the application,
            such as ``qiskit-experiments`` to implement the preferences.

        Returns:
            Dict: The experiment preferences.
        """
        return self._account.preferences

    @staticmethod
    def delete_account(name: Optional[str] = None) -> bool:
        """Delete a saved account from disk.

        Args:
            name: Name of the saved account to delete.
            auth: Authentication type of the default account to delete.
                Ignored if account name is provided.

        Returns:
            True if the account was deleted.
            False if no account was found.
        """

        return AccountManager.delete(name=name)
