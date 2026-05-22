"""
A few classes/resources that let you use a lazily created boto resource/client,
in a thread-safe manner:

Normally, you would just get it via an attribute name, in this version you

>>> boto_clients.ssm.get_paginator()

Or you can import it like so:

>>> from xboto.client import ssm
>>> ssm.get_paginator()

Same with resources:

>>> boto_resources.dynamodb.Table("some-table")

Or

>>> from xboto.client import dynamodb
>>> dynamodb.Table("some-table")
"""
from typing import Any, Optional, Dict, Type, Callable

import boto3
from botocore.session import Session
from xinject import Dependency, XContext
import xbool


class BotoSession(Dependency):
    """
    You can use this as an easy way to get a shared boto-session for the current thread.

    Right now only used with `_Loader` subclasses such as `BotoClients` and `BotoResources`.

    Boto Sessions are NOT thread-safe.
    When user is not using a session to create a client/resource,
    boto3 uses an internal/default session instead which is not thread-safe.

    - Or the docs for boto about this:
        - https://boto3.amazonaws.com/v1/documentation/api/latest/guide/session.html
    - For various examples see issue where people talk about it:
        - https://github.com/boto/botocore/issues/1246
    """

    @property
    def session(self) -> boto3.Session:
        if session := self._session:
            return session
        session = boto3.Session(**self._session_kwargs)
        self._session = session
        return session

    def __init__(
            self, *,
            reset_session_when_activated=False,
            aws_access_key_id: Optional[str] = None,
            aws_secret_access_key: Optional[str] = None,
            aws_session_token: Optional[str] = None,
            region_name: Optional[str] = None,
            botocore_session: Optional[Session] = None,
            profile_name: Optional[str] = None,
            **session_kwargs
    ):
        """

        Args:
            reset_session_when_activated: If True: when self is activated
                (ie: made the current resource/dependency)
                will automatically call `BotoSession.reset_session()`, and therefore next time
                `BotoSession.session` is asked for will lazily allocate new boto Session.
                This is useful for unit-tests, where you really do want to create a new
                session/connection each time the unit-test is called if you use
                `BotoSession` as a decorator to a unit-testing method.

                If False (default): will keep any session that has been previously/lazily created.
                This keeps the connections around for you; hence why it's the default option.

            aws_access_key_id (str):  access key ID
            aws_secret_access_key (str): AWS secret access key
            aws_session_token (str): AWS temporary session token
            region_name (str): Default region when creating new connections
            botocore_session (botocore.session.Session): Use this Botocore session instead of
                creating a new default one.
            profile_name (str): The name of a profile to use. If not given, then the default
                profile is used.
            **session_kwargs: Pass additional args for boto Session here
                (for additional args that boto3 might add in the future).
        """
        # Easily grab all boto args passed into us...
        args = {k: v for k, v in locals().items() if v is not None}
        args.pop('self', None)
        args.pop('reset_session_when_activated', None)
        args.pop('session_kwargs', None)

        # Remember args...
        self.reset_session_when_activated = reset_session_when_activated
        self._session_kwargs = {**args, **session_kwargs}
        self._boto_obj_store = {}

    def context_resource_for_copy(
            self, *, current_context: XContext, copied_context: XContext
    ) -> 'BotoSession':
        if self.reset_session_when_activated:
            self.reset_session()
        return self

    @property
    def session_kwargs(self) -> Dict[str, Any]:
        return self._session_kwargs.copy()

    @session_kwargs.setter
    def session_kwargs(self, value: Dict[str, Any]):
        self._session_kwargs = {**value}
        self.reset_session()

    def reset_session(self):
        # We will lazily create session and their associated boto-objs in the future as needed.
        self._session = None
        self._boto_obj_store = {}

    _session: Optional[boto3.Session] = None
    _session_kwargs: dict
    _boto_obj_store: dict

    def _boto_obj_for_dependency(
            self,
            dependency: '_BaseBotoClientOrResource',
            constructor: Callable,
            force_create: bool = False
    ):
        if not force_create and (boto_obj := self._boto_obj_store.get(dependency)):
            return boto_obj

        boto_obj = constructor()
        self._boto_obj_store[dependency] = boto_obj
        return boto_obj

    def _reset_boto_obj_for_dependency(self, dependency: '_BaseBotoClientOrResource'):
        self._boto_obj_store.pop(dependency, None)


boto_session = BotoSession.proxy()
""" You can use this as the current 'boto' session object.
    `_Loader` subclasses use this right now (see below).
"""


# TODO: Need to separate `xboto_kwargs` configuration from the actual resource,
#   so the configuration can be global while the resource is pre-thread.
#   For now, to get by until I have time to do the separation:
#       temporary look at a environmental variable to decide if we should make
#       the clients/resources thread-sharable or not.
class _BaseBotoClientOrResource(Dependency, thread_sharable=xbool.bool_env('XBOTO_THREAD_SHARABLE')):
    # Class Vars
    _boto_name: str = ''
    _boto_kind: str = ''

    # Instance Vars

    # These are used to keep track of how we configure(d) the boto client/resource.
    _boto_kwargs: Dict[str, Any]

    def __init__(
            self, region_name=None,
            api_version=None,
            use_ssl=None,
            verify=None,
            endpoint_url=None,
            aws_access_key_id=None,
            aws_secret_access_key=None,
            aws_session_token=None,
            config=None,
            **boto_kwargs
    ):
        """
        You can specify any of the boto client/resource args, the known ones have been
        specififed and documented out.
        
        If there are ones in the future that are new or we don't know about, you can
        still specify them, they will be passed to us in `boto_kwargs`, which will be
        used as addtional kwargs when creating new boto client/resource.
        
        Args:
            region_name: The name of the region associated with the client. A client is associated
                with a single region.
            api_version: The API version to use. By default, botocore will use the latest API
                version when creating a client.You only need to specify this parameter if you want
                to use a previous API version of the client.
            use_ssl: Whether or not to use SSL. By default, SSL is used. Note that not all
                services support non-ssl connections.
            verify: Whether or not to verify SSL certificates. By default SSL certificates are
                verified. You can provide the following values:

                - False - do not validate SSL certificates. SSL will still be used
                    (unless use_ssl is False), but SSL certificates will not be verified.
                - path/to/cert/bundle.pem - A filename of the CA cert bundle to uses.
                    You can specify this argument if you want to use a different CA cert bundle
                    than the one used by botocore.
            endpoint_url: The complete URL to use for the constructed client.
                Normally, botocore will automatically construct the appropriate URL to use when
                communicating with a service. You can specify a complete URL
                (including the "http/https" scheme) to override this behavior.
                If this value is provided, then use_ssl is ignored.
            aws_access_key_id: The access key to use when creating the client.
                This is entirely optional, and if not provided, the credentials configured for the
                session will automatically be used. You only need to provide this argument if you
                want to override the credentials used for this specific client.
            aws_secret_access_key: The secret key to use when creating the client.
                Same semantics as aws_access_key_id above.
            aws_session_token: The session token to use when creating the client.
                Same semantics as aws_access_key_id above.
            config: Advanced client configuration options.
                If region_name is specified in the client config, its value will take precedence
                over environment variables and configuration values, but not over a region_name
                value passed explicitly to the method. If user_agent_extra is specified in the
                client config, it overrides the default user_agent_extra provided by the resource
                API. See
                [botocore config documentation](https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html)
                for more details.
            **boto_kwargs:
        """  # noqa -- url can't be broken up.
        # Easily grab all boto args passed into us...
        args = {k: v for k, v in locals().items() if v is not None}
        args.pop('self', None)
        args.pop('boto_kwargs', None)

        self._boto_kwargs = {**args, **boto_kwargs}

    def __init_subclass__(cls, boto_name: str = '', boto_kind: str = '', **kwargs):
        super().__init_subclass__(**kwargs)
        cls._boto_name = boto_name
        cls._boto_kind = boto_kind

    def reset(self):
        """ Resets the client; it will be re-created lazily next time it's asked for.
        """
        # noinspection PyProtectedMember
        BotoSession.grab()._reset_boto_obj_for_dependency(self)

    def get(self):
        # If user specified their own 'endpoint_url', we are not using the default.
        # Otherwise, check to make sure settings value is still same as what we used;
        # we want a new object if the default endpoint_url has changed...
        #
        # For now, we just throw-away any old object if default has changed and user did not
        # specify their own endpoint_url value. If it changes frequently for some reason we
        # could optimize by store a client per-endpoint_url value, so we can reuse old
        # client when old values are restored.

        def constructor():
            # `kind` is either 'client' or 'resource', we get the correct creation method...
            boto_creation_method = getattr(boto_session.session, self._boto_kind)

            # We then call creation method with the resource/client name and any other kwargs;
            # For the kwargs, we start with any defaults and then add in user specified ones...
            return boto_creation_method(
                self._boto_name, **self._boto_kwargs
            )

        # noinspection PyProtectedMember
        return BotoSession.grab()._boto_obj_for_dependency(self, constructor)

    @classmethod
    def _get_dependency_cls(cls, boto_name: str) -> 'Type[_BaseBotoClientOrResource]':
        boto_kind = cls._boto_kind

        # Normalize name...
        # Client/Resources names never use `_`, they use a `-` instead.
        # Replace any `_` with a `-`
        # (allows one to still get it via attributes, vs having to pass a str into a/the method)
        boto_name = boto_name.replace("_", "-")
        boto_name = boto_name.lower()

        if boto_name.endswith("-"):
            # Remove ending underscore (ie: for the `lambda_` name).
            boto_name = boto_name[:-1]

        if dep_cls := _dependency_classes[boto_kind].get(boto_name):
            return dep_cls

        # We are creating a new type/class lazily based on the required boto resource/client...
        cls_name = f'{boto_name.capitalize()}{boto_kind.capitalize()}'
        dep_cls: Any = type(cls_name, (cls,), {}, boto_name=boto_name, boto_kind=boto_kind)

        # Store the type for future use.
        _dependency_classes[boto_kind][boto_name] = dep_cls
        return dep_cls

    @classmethod
    def get_dependency_cls(cls, boto_name: str) -> 'Type[_BaseBotoClientOrResource]':
        raise NotImplementedError("Need to implement `get_dependency_cls` class method")

    @property
    def boto_kwargs(self) -> Dict[str, Any]:
        """
        Returns a copy of the boto_kwargs assigned either while creating object in init
        `_BaseBotoClientOrResource.__init__ or changed via `boto_kwargs` setter property
        after it was created.

        Any settings defined in dict will be passed to boto-client/resource when it's lazily
        created.
        """
        return self._boto_kwargs.copy()

    @boto_kwargs.setter
    def boto_kwargs(self, value: Dict[str, Any]):
        """
        Makes a copy of value and will use them as the boto_kwargs.

        Any settings defined in dict will be passed to boto-client/resource when it's lazily
        created.

        After property is set, will call `_BaseBotoClientOrResource.reset` so that the next
        time that a boto-client/resource is asked of me I'll lazily create a new client/resource
        with the setting provided to this property-setter.
        """
        self._boto_kwargs = {**value}
        self.reset()


class BotoClient(_BaseBotoClientOrResource, boto_kind='client'):
    @property
    def boto_client(self):
        return self.get()

    @classmethod
    def get_dependency_cls(cls, boto_name: str) -> 'Type[BotoClient]':
        return cls._get_dependency_cls(boto_name)


class BotoResource(_BaseBotoClientOrResource, boto_kind='resource'):
    @property
    def boto_resource(self):
        return self.get()

    @classmethod
    def get_dependency_cls(cls, boto_name: str) -> 'Type[BotoResource]':
        return cls._get_dependency_cls(boto_name)


_dependency_classes: Dict[str, Dict[str, Type[BotoClient]]] = {
    'resource': {},
    'client': {}
}


class _LoaderMetaclass(type):
    _boto_dependency_class: Type[_BaseBotoClientOrResource]

    def __getattr__(self, key: str):
        if not key[0].isupper():
            raise AttributeError(
                f"BotoClient/BotoResource classes start with an upper-case char, "
                f"was instead given ({key})."
            )
        try:
            return self._boto_dependency_class.get_dependency_cls(key)
        except Exception as e:
            raise AttributeError(
                f"BotoClient/BotoResource class does not exist for key ({key}) "
                f"start with an upper-case char, was instead given ({key})."
            )


class _Loader(Dependency, metaclass=_LoaderMetaclass):
    def __init_subclass__(
            cls, boto_dependency_class: Optional[Type[_BaseBotoClientOrResource]] = None, **kwargs
    ):
        assert boto_dependency_class, (
            f"Subclass {cls} need to pass in `boto_dependency_class` class arg."
        )
        cls._boto_dependency_class = boto_dependency_class

    def load(self, module):
        """
        This is a way you can use a dynamic string to grab a boto3 client/resource by name.

        Normally, you would want to use one of these ways of doing it instead:

        >>> from xboto import boto_clients
        >>> boto_clients.ssm

        Or you can import it like so:

        >>> from xboto.client import ssm

        And then you can use this ssm client just like the real one:

        >>> ssm.get_paginator(...)

        There are also equivelent things for resources (like the client examples above)
        at `xboto.resource` and `xboto.boto_resources`.

        If you want to use a normal string to look up the client or resource,
        that's when you can use this load method.

        You can look up a boto3 client/resource via this method by passing in its name.
        You'll want to use a subclass of `_Loader` such as `BotoClients` or `BotoResources`.

        See thoese classes for more details, here are some quick examples:

        >>> BotoResources.grab().load('dynamodb')

        or

        >>> boto_resources.load('dynamodb')

        or

        >>> BotoClients.grab().load('ssm')

        or

        >>> boto_clients.load('ssm')
        """

        # We cache the clients/resources directly on 'self' (object),
        # using `module` as the attr-name (see `_Loader.__getattr__`)
        return getattr(self, module)

    def _lookup(self, module):
        """Implemented in subclasses to look up the module from boto3 properly."""
        raise NotImplementedError(f"Need to implement `_lookup` in subclass ({self}).")

    def __getattribute__(self, item):
        """
        Grabs a client/resource and stores it on self, returns it.

        Args:
            item: item-name to get

        Returns:

        """
        try:
            return super().__getattribute__(item)
        except AttributeError:
            client = self._lookup(item)
            return client


class BotoClients(_Loader, boto_dependency_class=BotoClient):
    """
    When you get an attribute off of me, I'll attempt to ask the boto3 library to allocate
    a client of the same type, and then store itself, so I return the same client again
    in the future.

    Right now, we will lazily allocate a boto3 client per-thread, and we will use the
    per-thread shared boto3 session resource to do it (ie: `_BotoSession.session`).

    You can also easily import and use the `boto_clients` proxy object
    (defined at top module-level).

    You can use `boto_clients` exactly the same as using `BotoClients.grab()`,
    making it more convenient to use since you can directly import `boto_clients`.

    >>> from xboto import boto_clients
    >>> # Showing here how you could use it:
    >>> boto_clients.ssm.get_paginator(...)

    If you have an aws client that uses a `-` for it's name, you can use an `_` (underscore)
    instead.
    All underscores are changed to a `-` when looking up the aws client.
    You can also directly use the `xboto.dependencies.BotoClients.load` method, and use a `-`
    there.
    """

    def _lookup(self, module):
        return BotoClient.get_dependency_cls(module).grab().boto_client

    # These annotations are only for IDE-type-completion;
    # any client boto supports will work regardless (even if not listed below).
    #
    # These are the xyn-resource `Resource` types/classes; ie: BotoClient subclasses
    # (start with upper-case letter)
    AccessAnalyzer: Type[BotoClient]
    Account: Type[BotoClient]
    Acm: Type[BotoClient]
    Acm_Pca: Type[BotoClient]
    AlexaForBusiness: Type[BotoClient]
    Amp: Type[BotoClient]
    Amplify: Type[BotoClient]
    AmplifyBackend: Type[BotoClient]
    AmplifyUiBuilder: Type[BotoClient]
    ApiGateway: Type[BotoClient]
    ApiGatewayManagementApi: Type[BotoClient]
    ApiGatewayV2: Type[BotoClient]
    AppConfig: Type[BotoClient]
    AppConfigData: Type[BotoClient]
    Appflow: Type[BotoClient]
    AppIntegrations: Type[BotoClient]
    Application_Autoscaling: Type[BotoClient]
    Application_Insights: Type[BotoClient]
    Applicationcostprofiler: Type[BotoClient]
    Appmesh: Type[BotoClient]
    Apprunner: Type[BotoClient]
    Appstream: Type[BotoClient]
    Appsync: Type[BotoClient]
    Arc_Zonal_Shift: Type[BotoClient]
    Athena: Type[BotoClient]
    AuditManager: Type[BotoClient]
    Autoscaling: Type[BotoClient]
    Autoscaling_Plans: Type[BotoClient]
    Backup: Type[BotoClient]
    Backup_Gateway: Type[BotoClient]
    BackupStorage: Type[BotoClient]
    Batch: Type[BotoClient]
    BillingConductor: Type[BotoClient]
    Braket: Type[BotoClient]
    Budgets: Type[BotoClient]
    Ce: Type[BotoClient]
    Chime: Type[BotoClient]
    Chime_Sdk_Identity: Type[BotoClient]
    Chime_Sdk_Media_Pipelines: Type[BotoClient]
    Chime_Sdk_Meetings: Type[BotoClient]
    Chime_Sdk_Messaging: Type[BotoClient]
    Chime_Sdk_Voice: Type[BotoClient]
    Cleanrooms: Type[BotoClient]
    Cloud9: Type[BotoClient]
    Cloudcontrol: Type[BotoClient]
    Clouddirectory: Type[BotoClient]
    Cloudformation: Type[BotoClient]
    Cloudfront: Type[BotoClient]
    Cloudhsm: Type[BotoClient]
    Cloudhsmv2: Type[BotoClient]
    Cloudsearch: Type[BotoClient]
    Cloudsearchdomain: Type[BotoClient]
    Cloudtrail: Type[BotoClient]
    Cloudtrail_Data: Type[BotoClient]
    Cloudwatch: Type[BotoClient]
    CodeArtifact: Type[BotoClient]
    CodeBuild: Type[BotoClient]
    CodeCatalyst: Type[BotoClient]
    CodeCommit: Type[BotoClient]
    CodeDeploy: Type[BotoClient]
    Codeguru_Reviewer: Type[BotoClient]
    CodeguruProfiler: Type[BotoClient]
    CodePipeline: Type[BotoClient]
    Codestar: Type[BotoClient]
    Codestar_Connections: Type[BotoClient]
    Codestar_Notifications: Type[BotoClient]
    Cognito_Identity: Type[BotoClient]
    Cognito_Idp: Type[BotoClient]
    Cognito_Sync: Type[BotoClient]
    Comprehend: Type[BotoClient]
    Comprehendmedical: Type[BotoClient]
    Compute_Optimizer: Type[BotoClient]
    Config: Type[BotoClient]
    Connect: Type[BotoClient]
    Connect_Contact_Lens: Type[BotoClient]
    ConnectCampaigns: Type[BotoClient]
    ConnectCases: Type[BotoClient]
    ConnectParticipant: Type[BotoClient]
    ControlTower: Type[BotoClient]
    Cur: Type[BotoClient]
    Customer_Profiles: Type[BotoClient]
    DataBrew: Type[BotoClient]
    DataExchange: Type[BotoClient]
    DataPipeline: Type[BotoClient]
    DataSync: Type[BotoClient]
    Dax: Type[BotoClient]
    Detective: Type[BotoClient]
    Devicefarm: Type[BotoClient]
    Devops_Guru: Type[BotoClient]
    DirectConnect: Type[BotoClient]
    Discovery: Type[BotoClient]
    Dlm: Type[BotoClient]
    Dms: Type[BotoClient]
    Docdb: Type[BotoClient]
    Docdb_Elastic: Type[BotoClient]
    Drs: Type[BotoClient]
    Ds: Type[BotoClient]
    DynamoDb: Type[BotoClient]
    DynamoDbStreams: Type[BotoClient]
    Ebs: Type[BotoClient]
    Ec2: Type[BotoClient]
    Ec2_Instance_Connect: Type[BotoClient]
    Ecr: Type[BotoClient]
    Ecr_Public: Type[BotoClient]
    Ecs: Type[BotoClient]
    Efs: Type[BotoClient]
    Eks: Type[BotoClient]
    Elastic_Inference: Type[BotoClient]
    Elasticache: Type[BotoClient]
    ElasticBeanstalk: Type[BotoClient]
    ElasticTranscoder: Type[BotoClient]
    Elb: Type[BotoClient]
    Elbv2: Type[BotoClient]
    Emr: Type[BotoClient]
    Emr_Containers: Type[BotoClient]
    Emr_Serverless: Type[BotoClient]
    Es: Type[BotoClient]
    Events: Type[BotoClient]
    Evidently: Type[BotoClient]
    Finspace: Type[BotoClient]
    Finspace_Data: Type[BotoClient]
    Firehose: Type[BotoClient]
    Fis: Type[BotoClient]
    Fms: Type[BotoClient]
    Forecast: Type[BotoClient]
    Forecastquery: Type[BotoClient]
    Frauddetector: Type[BotoClient]
    Fsx: Type[BotoClient]
    Gamelift: Type[BotoClient]
    Gamesparks: Type[BotoClient]
    Glacier: Type[BotoClient]
    Globalaccelerator: Type[BotoClient]
    Glue: Type[BotoClient]
    Grafana: Type[BotoClient]
    Greengrass: Type[BotoClient]
    Greengrassv2: Type[BotoClient]
    Groundstation: Type[BotoClient]
    Guardduty: Type[BotoClient]
    Health: Type[BotoClient]
    Healthlake: Type[BotoClient]
    Honeycode: Type[BotoClient]
    Iam: Type[BotoClient]
    IdentityStore: Type[BotoClient]
    ImageBuilder: Type[BotoClient]
    ImportExport: Type[BotoClient]
    Inspector: Type[BotoClient]
    Inspector2: Type[BotoClient]
    Iot: Type[BotoClient]
    Iot_Data: Type[BotoClient]
    Iot_Jobs_Data: Type[BotoClient]
    Iot_Roborunner: Type[BotoClient]
    Iot1Click_Devices: Type[BotoClient]
    Iot1Click_Projects: Type[BotoClient]
    IotAnalytics: Type[BotoClient]
    IotDeviceAdvisor: Type[BotoClient]
    IotEvents: Type[BotoClient]
    IotEvents_Data: Type[BotoClient]
    IotFleethub: Type[BotoClient]
    IotFleetwise: Type[BotoClient]
    IotSecureTunneling: Type[BotoClient]
    IotSitewise: Type[BotoClient]
    IotThingsgraph: Type[BotoClient]
    IotTwinmaker: Type[BotoClient]
    IotWireless: Type[BotoClient]
    Ivs: Type[BotoClient]
    Ivschat: Type[BotoClient]
    Kafka: Type[BotoClient]
    Kafkaconnect: Type[BotoClient]
    Kendra: Type[BotoClient]
    Kendra_Ranking: Type[BotoClient]
    Keyspaces: Type[BotoClient]
    Kinesis: Type[BotoClient]
    Kinesis_Video_Archived_Media: Type[BotoClient]
    Kinesis_Video_Media: Type[BotoClient]
    Kinesis_Video_Signaling: Type[BotoClient]
    Kinesis_Video_Webrtc_Storage: Type[BotoClient]
    KinesisAnalytics: Type[BotoClient]
    KinesisAnalyticsv2: Type[BotoClient]
    Kinesisvideo: Type[BotoClient]
    Kms: Type[BotoClient]
    Lakeformation: Type[BotoClient]
    # Lambda Is A Key-Word, Underscore Is Ignored.
    Lambda_: Type[BotoClient]
    Lex_Models: Type[BotoClient]
    Lex_Runtime: Type[BotoClient]
    Lexv2_Models: Type[BotoClient]
    Lexv2_Runtime: Type[BotoClient]
    License_Manager: Type[BotoClient]
    License_Manager_Linux_Subscriptions: Type[BotoClient]
    License_Manager_User_Subscriptions: Type[BotoClient]
    Lightsail: Type[BotoClient]
    Location: Type[BotoClient]
    Logs: Type[BotoClient]
    LookoutEquipment: Type[BotoClient]
    LookoutMetrics: Type[BotoClient]
    LookoutVision: Type[BotoClient]
    M2: Type[BotoClient]
    MachineLearning: Type[BotoClient]
    Macie: Type[BotoClient]
    Macie2: Type[BotoClient]
    ManagedBlockchain: Type[BotoClient]
    MarketPlace_Catalog: Type[BotoClient]
    MarketPlace_Entitlement: Type[BotoClient]
    MarketPlacecommerceanalytics: Type[BotoClient]
    MediaConnect: Type[BotoClient]
    MediaConvert: Type[BotoClient]
    MediaLive: Type[BotoClient]
    MediaPackage: Type[BotoClient]
    MediaPackage_Vod: Type[BotoClient]
    MediaStore: Type[BotoClient]
    MediaStore_Data: Type[BotoClient]
    MediaTailor: Type[BotoClient]
    MemoryDb: Type[BotoClient]
    MeteringMarketplace: Type[BotoClient]
    Mgh: Type[BotoClient]
    Mgn: Type[BotoClient]
    Migration_Hub_Refactor_Spaces: Type[BotoClient]
    MigrationHub_Config: Type[BotoClient]
    MigrationHubOrchestrator: Type[BotoClient]
    MigrationHubStrategy: Type[BotoClient]
    Mobile: Type[BotoClient]
    Mq: Type[BotoClient]
    Mturk: Type[BotoClient]
    Mwaa: Type[BotoClient]
    Neptune: Type[BotoClient]
    Network_Firewall: Type[BotoClient]
    Networkmanager: Type[BotoClient]
    Nimble: Type[BotoClient]
    Oam: Type[BotoClient]
    Omics: Type[BotoClient]
    Opensearch: Type[BotoClient]
    OpensearchServerless: Type[BotoClient]
    Opsworks: Type[BotoClient]
    Opsworkscm: Type[BotoClient]
    Organizations: Type[BotoClient]
    Outposts: Type[BotoClient]
    Panorama: Type[BotoClient]
    Personalize: Type[BotoClient]
    Personalize_Events: Type[BotoClient]
    Personalize_Runtime: Type[BotoClient]
    Pi: Type[BotoClient]
    Pinpoint: Type[BotoClient]
    Pinpoint_Email: Type[BotoClient]
    Pinpoint_Sms_Voice: Type[BotoClient]
    Pinpoint_Sms_Voice_V2: Type[BotoClient]
    Pipes: Type[BotoClient]
    Polly: Type[BotoClient]
    Pricing: Type[BotoClient]
    Privatenetworks: Type[BotoClient]
    Proton: Type[BotoClient]
    Qldb: Type[BotoClient]
    Qldb_Session: Type[BotoClient]
    Quicksight: Type[BotoClient]
    Ram: Type[BotoClient]
    Rbin: Type[BotoClient]
    Rds: Type[BotoClient]
    Rds_Data: Type[BotoClient]
    Redshift: Type[BotoClient]
    Redshift_Data: Type[BotoClient]
    Redshift_Serverless: Type[BotoClient]
    Rekognition: Type[BotoClient]
    Resiliencehub: Type[BotoClient]
    Resource_Explorer_2: Type[BotoClient]
    Resource_Groups: Type[BotoClient]
    ResourceGroupStaggingApi: Type[BotoClient]
    Robomaker: Type[BotoClient]
    Rolesanywhere: Type[BotoClient]
    Route53: Type[BotoClient]
    Route53_Recovery_Cluster: Type[BotoClient]
    Route53_Recovery_Control_Config: Type[BotoClient]
    Route53_Recovery_Readiness: Type[BotoClient]
    Route53Domains: Type[BotoClient]
    Route53Resolver: Type[BotoClient]
    Rum: Type[BotoClient]
    S3: Type[BotoClient]
    S3Control: Type[BotoClient]
    S3Outposts: Type[BotoClient]
    Sagemaker: Type[BotoClient]
    Sagemaker_A2I_Runtime: Type[BotoClient]
    Sagemaker_Edge: Type[BotoClient]
    Sagemaker_Featurestore_Runtime: Type[BotoClient]
    Sagemaker_Geospatial: Type[BotoClient]
    Sagemaker_Metrics: Type[BotoClient]
    Sagemaker_Runtime: Type[BotoClient]
    SavingsPlans: Type[BotoClient]
    Scheduler: Type[BotoClient]
    Schemas: Type[BotoClient]
    Sdb: Type[BotoClient]
    Secretsmanager: Type[BotoClient]
    Securityhub: Type[BotoClient]
    Securitylake: Type[BotoClient]
    Serverlessrepo: Type[BotoClient]
    Service_Quotas: Type[BotoClient]
    ServiceCatalog: Type[BotoClient]
    ServiceCatalog_Appregistry: Type[BotoClient]
    ServiceDiscovery: Type[BotoClient]
    Ses: Type[BotoClient]
    Sesv2: Type[BotoClient]
    Shield: Type[BotoClient]
    Signer: Type[BotoClient]
    Simspaceweaver: Type[BotoClient]
    Sms: Type[BotoClient]
    Sms_Voice: Type[BotoClient]
    Snow_Device_Management: Type[BotoClient]
    Snowball: Type[BotoClient]
    Sns: Type[BotoClient]
    Sqs: Type[BotoClient]
    Ssm: Type[BotoClient]
    Ssm_Contacts: Type[BotoClient]
    Ssm_Incidents: Type[BotoClient]
    Ssm_Sap: Type[BotoClient]
    Sso: Type[BotoClient]
    Sso_Admin: Type[BotoClient]
    Sso_Oidc: Type[BotoClient]
    StepFunctions: Type[BotoClient]
    StorageGateway: Type[BotoClient]
    Sts: Type[BotoClient]
    Support: Type[BotoClient]
    Support_App: Type[BotoClient]
    Swf: Type[BotoClient]
    Synthetics: Type[BotoClient]
    Textract: Type[BotoClient]
    Timestream_Query: Type[BotoClient]
    Timestream_Write: Type[BotoClient]
    Transcribe: Type[BotoClient]
    Transfer: Type[BotoClient]
    Translate: Type[BotoClient]
    Voice_Id: Type[BotoClient]
    Waf: Type[BotoClient]
    Waf_Regional: Type[BotoClient]
    Wafv2: Type[BotoClient]
    WellArchitected: Type[BotoClient]
    Wisdom: Type[BotoClient]
    Workdocs: Type[BotoClient]
    Worklink: Type[BotoClient]
    Workmail: Type[BotoClient]
    WorkmailMessageFlow: Type[BotoClient]
    Workspaces: Type[BotoClient]
    Workspaces_Web: Type[BotoClient]
    Xray: Type[BotoClient]

    # These annotations are only for IDE-type-completion;
    # any client boto supports will work regardless (even if not listed below).
    #
    # These are the boto client objects (start with lower-case letter)
    accessanalyzer: Any
    account: Any
    acm: Any
    acm_pca: Any
    alexaforbusiness: Any
    amp: Any
    amplify: Any
    amplifybackend: Any
    amplifyuibuilder: Any
    apigateway: Any
    apigatewaymanagementapi: Any
    apigatewayv2: Any
    appconfig: Any
    appconfigdata: Any
    appflow: Any
    appintegrations: Any
    application_autoscaling: Any
    application_insights: Any
    applicationcostprofiler: Any
    appmesh: Any
    apprunner: Any
    appstream: Any
    appsync: Any
    arc_zonal_shift: Any
    athena: Any
    auditmanager: Any
    autoscaling: Any
    autoscaling_plans: Any
    backup: Any
    backup_gateway: Any
    backupstorage: Any
    batch: Any
    billingconductor: Any
    braket: Any
    budgets: Any
    ce: Any
    chime: Any
    chime_sdk_identity: Any
    chime_sdk_media_pipelines: Any
    chime_sdk_meetings: Any
    chime_sdk_messaging: Any
    chime_sdk_voice: Any
    cleanrooms: Any
    cloud9: Any
    cloudcontrol: Any
    clouddirectory: Any
    cloudformation: Any
    cloudfront: Any
    cloudhsm: Any
    cloudhsmv2: Any
    cloudsearch: Any
    cloudsearchdomain: Any
    cloudtrail: Any
    cloudtrail_data: Any
    cloudwatch: Any
    codeartifact: Any
    codebuild: Any
    codecatalyst: Any
    codecommit: Any
    codedeploy: Any
    codeguru_reviewer: Any
    codeguruprofiler: Any
    codepipeline: Any
    codestar: Any
    codestar_connections: Any
    codestar_notifications: Any
    cognito_identity: Any
    cognito_idp: Any
    cognito_sync: Any
    comprehend: Any
    comprehendmedical: Any
    compute_optimizer: Any
    config: Any
    connect: Any
    connect_contact_lens: Any
    connectcampaigns: Any
    connectcases: Any
    connectparticipant: Any
    controltower: Any
    cur: Any
    customer_profiles: Any
    databrew: Any
    dataexchange: Any
    datapipeline: Any
    datasync: Any
    dax: Any
    detective: Any
    devicefarm: Any
    devops_guru: Any
    directconnect: Any
    discovery: Any
    dlm: Any
    dms: Any
    docdb: Any
    docdb_elastic: Any
    drs: Any
    ds: Any
    dynamodb: Any
    dynamodbstreams: Any
    ebs: Any
    ec2: Any
    ec2_instance_connect: Any
    ecr: Any
    ecr_public: Any
    ecs: Any
    efs: Any
    eks: Any
    elastic_inference: Any
    elasticache: Any
    elasticbeanstalk: Any
    elastictranscoder: Any
    elb: Any
    elbv2: Any
    emr: Any
    emr_containers: Any
    emr_serverless: Any
    es: Any
    events: Any
    evidently: Any
    finspace: Any
    finspace_data: Any
    firehose: Any
    fis: Any
    fms: Any
    forecast: Any
    forecastquery: Any
    frauddetector: Any
    fsx: Any
    gamelift: Any
    gamesparks: Any
    glacier: Any
    globalaccelerator: Any
    glue: Any
    grafana: Any
    greengrass: Any
    greengrassv2: Any
    groundstation: Any
    guardduty: Any
    health: Any
    healthlake: Any
    honeycode: Any
    iam: Any
    identitystore: Any
    imagebuilder: Any
    importexport: Any
    inspector: Any
    inspector2: Any
    iot: Any
    iot_data: Any
    iot_jobs_data: Any
    iot_roborunner: Any
    iot1click_devices: Any
    iot1click_projects: Any
    iotanalytics: Any
    iotdeviceadvisor: Any
    iotevents: Any
    iotevents_data: Any
    iotfleethub: Any
    iotfleetwise: Any
    iotsecuretunneling: Any
    iotsitewise: Any
    iotthingsgraph: Any
    iottwinmaker: Any
    iotwireless: Any
    ivs: Any
    ivschat: Any
    kafka: Any
    kafkaconnect: Any
    kendra: Any
    kendra_ranking: Any
    keyspaces: Any
    kinesis: Any
    kinesis_video_archived_media: Any
    kinesis_video_media: Any
    kinesis_video_signaling: Any
    kinesis_video_webrtc_storage: Any
    kinesisanalytics: Any
    kinesisanalyticsv2: Any
    kinesisvideo: Any
    kms: Any
    lakeformation: Any
    # Lambda is a key-word, underscore is ignored.
    lambda_: Any
    lex_models: Any
    lex_runtime: Any
    lexv2_models: Any
    lexv2_runtime: Any
    license_manager: Any
    license_manager_linux_subscriptions: Any
    license_manager_user_subscriptions: Any
    lightsail: Any
    location: Any
    logs: Any
    lookoutequipment: Any
    lookoutmetrics: Any
    lookoutvision: Any
    m2: Any
    machinelearning: Any
    macie: Any
    macie2: Any
    managedblockchain: Any
    marketplace_catalog: Any
    marketplace_entitlement: Any
    marketplacecommerceanalytics: Any
    mediaconnect: Any
    mediaconvert: Any
    medialive: Any
    mediapackage: Any
    mediapackage_vod: Any
    mediastore: Any
    mediastore_data: Any
    mediatailor: Any
    memorydb: Any
    meteringmarketplace: Any
    mgh: Any
    mgn: Any
    migration_hub_refactor_spaces: Any
    migrationhub_config: Any
    migrationhuborchestrator: Any
    migrationhubstrategy: Any
    mobile: Any
    mq: Any
    mturk: Any
    mwaa: Any
    neptune: Any
    network_firewall: Any
    networkmanager: Any
    nimble: Any
    oam: Any
    omics: Any
    opensearch: Any
    opensearchserverless: Any
    opsworks: Any
    opsworkscm: Any
    organizations: Any
    outposts: Any
    panorama: Any
    personalize: Any
    personalize_events: Any
    personalize_runtime: Any
    pi: Any
    pinpoint: Any
    pinpoint_email: Any
    pinpoint_sms_voice: Any
    pinpoint_sms_voice_v2: Any
    pipes: Any
    polly: Any
    pricing: Any
    privatenetworks: Any
    proton: Any
    qldb: Any
    qldb_session: Any
    quicksight: Any
    ram: Any
    rbin: Any
    rds: Any
    rds_data: Any
    redshift: Any
    redshift_data: Any
    redshift_serverless: Any
    rekognition: Any
    resiliencehub: Any
    resource_explorer_2: Any
    resource_groups: Any
    resourcegroupstaggingapi: Any
    robomaker: Any
    rolesanywhere: Any
    route53: Any
    route53_recovery_cluster: Any
    route53_recovery_control_config: Any
    route53_recovery_readiness: Any
    route53domains: Any
    route53resolver: Any
    rum: Any
    s3: Any
    s3control: Any
    s3outposts: Any
    sagemaker: Any
    sagemaker_a2i_runtime: Any
    sagemaker_edge: Any
    sagemaker_featurestore_runtime: Any
    sagemaker_geospatial: Any
    sagemaker_metrics: Any
    sagemaker_runtime: Any
    savingsplans: Any
    scheduler: Any
    schemas: Any
    sdb: Any
    secretsmanager: Any
    securityhub: Any
    securitylake: Any
    serverlessrepo: Any
    service_quotas: Any
    servicecatalog: Any
    servicecatalog_appregistry: Any
    servicediscovery: Any
    ses: Any
    sesv2: Any
    shield: Any
    signer: Any
    simspaceweaver: Any
    sms: Any
    sms_voice: Any
    snow_device_management: Any
    snowball: Any
    sns: Any
    sqs: Any
    ssm: Any
    ssm_contacts: Any
    ssm_incidents: Any
    ssm_sap: Any
    sso: Any
    sso_admin: Any
    sso_oidc: Any
    stepfunctions: Any
    storagegateway: Any
    sts: Any
    support: Any
    support_app: Any
    swf: Any
    synthetics: Any
    textract: Any
    timestream_query: Any
    timestream_write: Any
    transcribe: Any
    transfer: Any
    translate: Any
    voice_id: Any
    waf: Any
    waf_regional: Any
    wafv2: Any
    wellarchitected: Any
    wisdom: Any
    workdocs: Any
    worklink: Any
    workmail: Any
    workmailmessageflow: Any
    workspaces: Any
    workspaces_web: Any
    xray: Any


class BotoResources(_Loader, boto_dependency_class=BotoResource):
    """
    When you get an attribute off of me, I'll attempt to ask the boto3 library to allocate
    a resource of the same type, and then store itself, so I return the same resource again
    in the future.

    Right now, we will lazily allocate a boto3 resource per-thread, and we will use the
    per-thread shared boto3 session resource to do it (ie: `_BotoSession.session`).

    You can also easily import and use the `boto_resources` proxy object
    (defined at top module-level).

    You can use `boto_resources` exactly the same as using `BotoResources.grab()`,
    making it more convenient to use since you can directly import `boto_resources`.

    >>> from xboto import boto_resources
    >>> # Showing here how you could use it to get a Table resource:
    >>> table = boto_resources.dynamodb.Table("some-table")

    If you have an aws resource that uses a `-` for it's name, you can use an `_` (underscore)
    instead.
    All underscores are changed to a `-` when looking up the aws resource.
    You can also directly use the `xboto.dependencies.BotoResources.load` method, and use a `-`
    there.
    """

    def _lookup(self, module, **kwargs):
        return BotoResource.get_dependency_cls(module).grab().boto_resource

    # These annotations are only for IDE-type-completion;
    # any client boto supports will work regardless (even if not listed below).
    #
    # These are the xyn-resource `Resource` types/classes; ie: BotoResource subclasses
    # (start with upper-case letter):
    DynamoDB: Type[BotoResource]
    CloudFormation: Type[BotoResource]
    CloudWatch: Type[BotoResource]
    Ec2: Type[BotoResource]
    Glacier: Type[BotoResource]
    Iam: Type[BotoResource]
    OpsWorks: Type[BotoResource]
    S3: Type[BotoResource]
    Ns: Type[BotoResource]
    Sqs: Type[BotoResource]

    # These annotations are only for IDE-type-completion;
    # any client boto supports will work regardless (even if not listed below).
    #
    # These are the boto resource objects (start with lower-case letter):
    dynamodb: Any
    cloudformation: Any
    cloudwatch: Any
    ec2: Any
    glacier: Any
    iam: Any
    opsworks: Any
    s3: Any
    ns: Any
    sqs: Any


boto_clients = BotoClients.proxy()
""" You can import this and then ask it for clients via attributes.

    Example:

    >>> from xboto import boto_clients
    >>>
    >>> # Get the ssm client (ask for it each time), then get it's paginator.
    >>> boto_clients.ssm.get_paginator(...)

    You can also directly import a client like so:

    >>> from xboto.client import ssm
    >>>
    >>> # You can just use it directly anytime you need too:
    >>> ssm.get_paginator()

    Or import top-level object only:

    >> import xboto
    >>
    >>> # You can just use any client you want:
    >>> xboto.client.ssm.get_paginator()
"""

boto_resources = BotoResources.proxy()
""" You can import this and then ask it for clients via attributes.

    Example:

    >>> from xboto import boto_resources FINISH HERE!!!!! ****
    >>>
    >>> # Get the ssm client (ask for it each time), then get it's paginator.
    >>> boto_resources.dynamodb.create_table()

    You can also directly import a client like so:

    >>> from xboto.resource import dynamodb
    >>>
    >>> # You can just use it directly anytime you need too:
    >>> dynamodb.create_table()

    Or import top-level object only:

    >> import xboto
    >>
    >>> # You can just use any client you want:
    >>> xboto.resource.dynamodb.create_table()
"""
