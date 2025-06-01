import argparse
import json
import time
import pymongo
import certifi
from datetime import datetime
import requests
import math

parser = argparse.ArgumentParser(description='Get SemaphoreCI info')
parser.add_argument('orgName', type=str,
                    help='Name of the SemaphoreCI organization. Example: maxzeger')
parser.add_argument('projectId', type=str,
                    help='ID of the SemaphoreCI project. Example: f7286167-bc04-4c4a-b8d1-516b6cfeefb3')
parser.add_argument('semaphoreApiToken', type=str,
                    help='API token from SemaphoreCI. Example: XxsQJtQ9F1oeBqQejFzT')
parser.add_argument('refreshTimer', type=int,
                    help='Seconds between each refresh. Example: 5')
args = parser.parse_args()

orgName = args.orgName
projectId = args.projectId
semaphoreApiToken = args.semaphoreApiToken
refreshTimer = int(args.refreshTimer)


mongoClient = pymongo.MongoClient("mongodb+srv://admin:admin@devopsvr.er5xpl5.mongodb.net", tlsCAFile=certifi.where())
database = mongoClient["DevOps"]
rawCollection = database["DevOpsRaw"]
collection = database["DevOpsFormatted"]

while True:
    response = requests.get(
        'https://' + orgName + '.semaphoreci.com/api/v1alpha/plumber-workflows?project_id=' + projectId,
        headers={'Authorization': 'Token ' + semaphoreApiToken}
    )
    workflowList = json.loads(response.text)
    for workflow in workflowList:
        response = requests.get(
            'https://' + orgName + '.semaphoreci.com/api/v1alpha/pipelines?wf_id=' + workflow['wf_id'],
            headers={'Authorization': 'Token ' + semaphoreApiToken}
        )
        pipelineList = json.loads(response.text)
        pipeline = pipelineList[0]
        response = requests.get(
            'https://' + orgName + '.semaphoreci.com/api/v1alpha/pipelines/'
            + pipeline['ppl_id'] + '?detailed=true',
            headers={'Authorization': 'Token ' + semaphoreApiToken}
        )
        pipelineDetail = json.loads(response.text)
        for block in pipelineDetail['blocks']:
            for job in block['jobs']:
                response = requests.get(
                    'https://' + orgName + '.semaphoreci.com/api/v1alpha/jobs/'
                    + job['job_id'],
                    headers={'Authorization': 'Token ' + semaphoreApiToken}
                )
                job['detail'] = json.loads(response.text)

        workflow['pipeline'] = pipelineDetail

    rawCollection.replace_one({'name': orgName + '-' + projectId}, {'name': orgName + '-' + projectId, 'source': 'SemaphoreCI', 'runs': workflowList}, True)
    print("Raw data has been written to database")

    formatted = []
    for workflow in workflowList:
        run = {}
        run['id'] = workflow['wf_id']
        run['name'] = workflow['pipeline']['pipeline']['name']
        state = workflow['pipeline']['pipeline']['state']

        if state == 'running':
            run['status'] = 'IN_PROGRESS'
        else:
            result = workflow['pipeline']['pipeline']['result']
            if result == 'passed' or result == 'PASSED':
                run['status'] = 'SUCCESS'
            elif result == 'failed':
                run['status'] = 'FAILED'
            else:
                run['status'] = result

        if state == 'running':
            run['durationMillis'] = math.floor((datetime.utcnow().timestamp() - datetime.strptime(workflow['pipeline']['pipeline']['running_at'], '%Y-%m-%d %H:%M:%S.%fZ').timestamp()) * 1000)
        else:
            run['durationMillis'] = math.floor((datetime.strptime(workflow['pipeline']['pipeline']['done_at'], '%Y-%m-%d %H:%M:%S.%fZ').timestamp() - datetime.strptime(workflow['pipeline']['pipeline']['running_at'], '%Y-%m-%d %H:%M:%S.%fZ').timestamp()) * 1000)

        run['stages'] = []
        for block in workflow['pipeline']['blocks']:
            stage = {}
            stage['id'] = block['block_id']
            stage['name'] = block['name']
            if block['state'] == 'running':
                stage['status'] = 'IN_PROGRESS'
            elif block['state'] == 'waiting':
                stage['status'] = 'WAITING'
            else:
                result = block['result']
                if result == 'passed' or result == 'PASSED':
                    stage['status'] = 'SUCCESS'
                elif result == 'failed':
                    stage['status'] = 'FAILED'
                else:
                    stage['status'] = result
            stage['description'] = []
            stage['errorMessage'] = block['error_description']

            stage['nodes'] = []
            for job in block['jobs']:
                node = {}
                node['id'] = job['job_id']
                node['name'] = job['name']
                if job['status'] == 'RUNNING':
                    node['status'] = 'IN_PROGRESS'
                else:
                    if job['result'] == 'PASSED':
                        node['status'] = 'SUCCESS'
                    else:
                        node['status'] = job['result']
                node['description'] = job['detail']['spec']['commands']
                node['errorMessage'] = block['error_description']
                if job['status'] == 'RUNNING':
                    node['durationMillis'] = math.floor((time.time() - int(job['detail']['metadata']['start_time'])) * 1000)
                elif node['status'] == 'SUCCESS' or node['status'] == 'FAILED':
                    node['durationMillis'] = math.floor((int(job['detail']['metadata']['finish_time']) - int(job['detail']['metadata']['start_time'])) * 1000)
                else:
                    node['durationMillis'] = 0
                stage['nodes'].append(node)
            if 'nodes' in stage and len(stage['nodes']) > 0:
                stage['durationMillis'] = max([node['durationMillis'] for node in stage['nodes']])
            else:
                stage['durationMillis'] = 0
            run['stages'].append(stage)
        formatted.append(run)

    collection.replace_one({'name': orgName + '-' + projectId}, {'name': orgName + '-' + projectId, 'runs': formatted}, True)
    print("Formatted data has been written to database")
    time.sleep(5)


