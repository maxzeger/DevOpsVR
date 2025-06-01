import argparse
import json
import time
import pymongo
import certifi
import requests


parser = argparse.ArgumentParser(description='Get Jenkins info')
parser.add_argument('baseUrl', type=str,
                    help='Base URL of Jenkins server. Example: http://localhost:8080')
parser.add_argument('jobName', type=str,
                    help='Name of the Jenkins job. Example: test')
parser.add_argument('refreshTimer', type=int,
                    help='Seconds between each refresh. Example: 5')
args = parser.parse_args()

baseUrl = args.baseUrl
jobName = args.jobName
refreshTimer = int(args.refreshTimer)

mongoClient = pymongo.MongoClient("mongodb+srv://admin:admin@devopsvr.er5xpl5.mongodb.net", tlsCAFile=certifi.where())
database = mongoClient["DevOps"]
rawCollection = database["DevOpsRaw"]
collection = database["DevOpsFormatted"]

while True:
    response = requests.get(baseUrl + '/job/' + jobName + '/wfapi/runs')
    pipelines = json.loads(response.text)
    detailStages = []
    for pipeline in pipelines:
        pipeline['detailStages'] = []
        for stage in pipeline['stages']:
            response = requests.get(baseUrl + stage['_links']['self']['href'])
            pipeline['detailStages'].append(json.loads(response.text))
    rawCollection.replace_one({'name': jobName}, {'name': jobName, 'source': 'Jenkins', 'runs': pipelines}, True)
    print("Raw data has been written to database")

    for run in pipelines:
        del run['_links'], run['startTimeMillis'], run['endTimeMillis'], run['queueDurationMillis']
        del run['pauseDurationMillis'], run['stages']
        run['stages'] = run.pop('detailStages')
        for stage in run['stages']:
            del stage['_links'], stage['execNode'], stage['startTimeMillis'], stage['pauseDurationMillis']
            stage['nodes'] = stage.pop('stageFlowNodes')
            if 'error' in stage:
                stage['errorMessage'] = stage['error']['message']
                del stage['error']
            else:
                stage['errorMessage'] = ''
            if 'parameterDescription' in stage:
                stage['description'] = [stage.pop('parameterDescription')]
            for node in stage['nodes']:
                del node['_links'], node['execNode'], node['startTimeMillis']
                del node['pauseDurationMillis'], node['parentNodes']
                if 'error' in node:
                    node['errorMessage'] = node['error']['message']
                    del node['error']
                else:
                    node['errorMessage'] = ''
                if 'parameterDescription' in node:
                    node['description'] = [node.pop('parameterDescription')]

        collection.replace_one({'name': jobName}, {'name': jobName, 'runs': pipelines}, True)
    print("Formatted data has been written to database")
    time.sleep(refreshTimer)


