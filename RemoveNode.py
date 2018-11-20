import boto3

client = boto3.client('elasticache', region_name='us-east-1')
cluster_id = 'scale-test'

response = client.describe_cache_clusters(CacheClusterId=cluster_id, ShowCacheNodeInfo=True)
count = response['CacheClusters'][0]['NumCacheNodes']
nodes = response['CacheClusters'][0]['CacheNodes']
id_to_remove = nodes[count - 1]['CacheNodeId']
response = client.modify_cache_cluster(CacheClusterId=cluster_id, NumCacheNodes=count - 1, CacheNodeIdsToRemove=[id_to_remove], ApplyImmediately=True)

print(response)
