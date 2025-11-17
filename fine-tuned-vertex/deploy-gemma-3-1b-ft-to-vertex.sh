#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | sed 's/#.*//g' | xargs)
fi

# setup python venv for model deployment
python -m venv venv
source venv/bin/activate

pip3 install --upgrade --quiet google-cloud-aiplatform
pip3 install openai google-auth requests

gcloud services enable aiplatform.googleapis.com --project=$PROJECT_ID
python deploy-gemma-3-1b-ft-to-vertex.py