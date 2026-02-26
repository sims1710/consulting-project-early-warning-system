# Live projects
curl.exe -X POST "$ES_URL/projects_live/_bulk" -H "Content-Type: application/x-ndjson" -H "Authorization: ApiKey $API_KEY" --data-binary "@projects_live.ndjson"

# Sentiment
curl.exe -X POST "$ES_URL/projects_sentiment/_bulk" -H "Content-Type: application/x-ndjson" -H "Authorization: ApiKey $API_KEY" --data-binary "@projects_sentiment.ndjson"

# Playbooks
curl.exe -X POST "$ES_URL/project_playbooks/_bulk" -H "Content-Type: application/x-ndjson" -H "Authorization: ApiKey $API_KEY" --data-binary "@project_playbooks.ndjson"

# Live timeseries projects
curl.exe -X POST "$ES_URL/projects_live_timeseries/_bulk" -H "Content-Type: application/x-ndjson" -H "Authorization: ApiKey $API_KEY" --data-binary "@projects_live_timeseries.ndjson"
