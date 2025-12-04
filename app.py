from flask import Flask, render_template, request
import requests
import os
import json
import re
import google.generativeai as genai
from github import Github, GithubException

app = Flask(__name__)

def sanitize_name(name):
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9-]', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')

def generate_files_with_gemini(app_name, app_description):
    genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f'Generate a simple Python Flask web app named {app_name}. Description: {app_description}. Return ONLY a valid JSON object with no markdown no code blocks no explanation. The JSON must have exactly these keys: app.py containing a complete Flask app with GET slash route returning a styled HTML page showing app name and description, requirements.txt containing only flask and gunicorn on separate lines, Dockerfile as a single string, render.yaml as a single string with runtime docker plan free name {app_name}, README.md with live URL https://{app_name}.onrender.com and run locally instructions'
    response = model.generate_content(prompt)
    text = response.text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)

def push_to_github(app_name, app_description, files):
    token = os.environ.get('GITHUB_TOKEN')
    g = Github(token)
    user = g.get_user()
    repo = user.create_repo(name=app_name, description=app_description, private=False, auto_init=False)
    for filename, content in files.items():
        repo.create_file(path=filename, message=f'feat: initial scaffold of {app_name}', content=content)
    return f'https://github.com/kantamnenisri/{app_name}'

def deploy_to_render(app_name):
    api_key = os.environ.get('RENDER_API_KEY')
    owner_id = os.environ.get('RENDER_OWNER_ID')
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
    payload = {'type': 'web_service', 'name': app_name, 'ownerId': owner_id, 'serviceDetails': {'runtime': 'docker', 'plan': 'free', 'pullRequestPreviewsEnabled': False}, 'repo': f'https://github.com/kantamnenisri/{app_name}', 'autoDeploy': 'yes'}
    response = requests.post('https://api.render.com/v1/services', headers=headers, json=payload, timeout=30)
    if response.status_code in [200, 201, 202]:
        return 'Auto-deployed on Render'
    else:
        return f'Manual deployment needed - Render API returned {response.status_code}: {response.text}'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return {'status': 'UP'}

@app.route('/create', methods=['POST'])
def create():
    try:
        app_name = sanitize_name(request.form.get('app_name', ''))
        app_description = request.form.get('app_description', '').strip()
        if not app_name:
            return render_template('result.html', status='error', error_message='Invalid app name. Use lowercase letters numbers and hyphens only.')
        if not app_description:
            return render_template('result.html', status='error', error_message='App description cannot be empty.')
        files = generate_files_with_gemini(app_name, app_description)
        github_url = push_to_github(app_name, app_description, files)
        render_status = deploy_to_render(app_name)
        render_url = f'https://{app_name}.onrender.com'
        return render_template('result.html', status='success', app_name=app_name, github_url=github_url, render_url=render_url, render_status=render_status)
    except GithubException as e:
        return render_template('result.html', status='error', error_message=f'GitHub error: Repo may already exist. Try a different name. Details: {str(e)}')
    except json.JSONDecodeError:
        return render_template('result.html', status='error', error_message='Gemini returned invalid JSON. Please try again.')
    except Exception as e:
        return render_template('result.html', status='error', error_message=f'Unexpected error: {str(e)}')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
