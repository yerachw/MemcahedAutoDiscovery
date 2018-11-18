import boto3
from pymemcache.client.hash import HashClient
import threading
import time
import json

class AutodiscoveryClient(HashClient):

    def __init__(self, cluster_id):
        self.elasticache = boto3.client('elasticache')
        self.cluster_id = cluster_id
        self.servers = self.new_server_list()
        super().__init__(self.servers, serializer=self.json_serializer, deserializer=self.json_deserializer, use_pooling=True)
        self.set(key='foo', value='HelloWorld', expire=1)
        print('Variable added')
        self.timer = threading.Timer(60, self.check_cluster)
        self.timer.start()

    def new_server_list(self):
        new_servers = []
        response = self.elasticache .describe_cache_clusters(CacheClusterId=self.cluster_id, ShowCacheNodeInfo=True)
        nodes = response['CacheClusters'][0]['CacheNodes']
        for node in nodes:
            endpoint = (node['Endpoint']['Address'], node['Endpoint']['Port'])
            new_servers.append(endpoint)
        return new_servers

    def check_cluster(self):
        print('Checking cluster')
        new_servers = self.new_server_list()

        for server, port in (set(new_servers) - set(self.servers)):
            print('Adding server {} on port'.format(server, port))
            self.add_server(server, port)

        for server, port in (set(self.servers) - set(new_servers)):
            print('Removing server {} on port'.format(server, port))
            self.remove_server(server, port)

        self.servers = new_servers

    def json_serializer(key, value):
        if type(value) == str:
            return value, 1
        return json.dumps(value), 2

    def json_deserializer(key, value, flags):
        if flags == 1:
            return value.decode('utf-8')
        if flags == 2:
            return json.loads(value.decode('utf-8'))
        raise Exception("Unknown serialization format")


cluster_id = 'scale-test'
memcached = AutodiscoveryClient(cluster_id)


def setVariable(self, variable_name, variable_value, expire_secs=0):
    memcached.set(key=variable_name, value=variable_value, expire=expire_secs)


def getVariable(self, variable_name):
    return memcached.get(variable_name)


def clearVariable(self, variable_name):
    memcached.delete(variable_name)


count = 1
while True:
    # set 10 new variables
    for i in range(1, 10):
        setVariable('foo_{}'.format(i+count), 'HelloWorld', 720)
 #       setVariable('foo_json_{}'.format(i+count), {'a': 'b', 'c': 'd'}, 720)

    time.sleep(10)

    # make sure we can get all variables back
    for i in range(1, 10):
        print(getVariable('foo_{}'.format(i+count)))
 #       print(getVariable('foo_json_{}'.format(i+count)))

    count = count + 10
