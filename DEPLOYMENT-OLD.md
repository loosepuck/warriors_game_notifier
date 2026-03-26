# Warriors Game Notifier - Google Cloud Deployment Guide

## Overview
This guide walks you through deploying the Warriors game notification system to Google Cloud Platform.

## Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed and authenticated
- Philips Hue Bridge ID and OAuth credentials (from Postman setup)
- Hue API certificate (.pem file)

## Architecture
The system consists of two Cloud Functions:
1. **morning-check**: Runs daily at 8 AM PT, checks for games, schedules notifications
2. **warriors-notification**: Triggered by Cloud Scheduler to activate Hue lights

## Step 1: Enable Required APIs

```bash
# Set your project ID
export PROJECT_ID="warriors-game-notifier"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable cloudtasks.googleapis.com
```

## Step 2: Store Secrets in Secret Manager

### 2.1 Create secrets for Hue credentials

```bash
# Hue Client ID
echo -n "2438f520-5cdc-4e07-a0ee-6991e6513c8c" | gcloud secrets create hue_client_id --data-file=-

# Hue Client Secret
echo -n "9bf0d60a7d905c8e94c5c03ab73454b0" | gcloud secrets create hue_client_secret --data-file=-

# Hue Refresh Token (from Postman)
echo -n "EnxitG01OwiZSo7WPiWL3RJ0tB4" | gcloud secrets create hue_refresh_token --data-file=-

echo -n "EnxitG01OwiZSo7WPiWL3RJ0tB4" | gcloud secrets versions add hue_refresh_token --data-file=-

# Hue Bridge ID
echo -n "jahhW0iyuXXPPvff42BB1mfkCN64AER5DyO5jCVZ" | gcloud secrets create hue_bridge_id --data-file=-
```

### 2.2 Store Hue Certificate

```bash
# Upload the certificate file
gcloud secrets create hue_certificate --data-file=/Users/brian/Desktop/hue1.pem
```

### 2.3 Grant Access to Cloud Functions Service Account

```bash
# Get the service account email
export SERVICE_ACCOUNT="9010317804-compute@developer.gserviceaccount.com"

# Grant access to all secrets
for secret in hue_client_id hue_client_secret hue_refresh_token hue_bridge_id hue_certificate; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"
done
```

# Grant Cloud Scheduler Admin role to the compute service account
gcloud projects add-iam-policy-binding warriors-game-notifier \
  --member="serviceAccount:9010317804-compute@developer.gserviceaccount.com" \
  --role="roles/cloudscheduler.admin"
  
  gcloud projects add-iam-policy-binding warriors-game-notifier \
  --member="serviceAccount:9010317804-compute@developer.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"
  
## Step 3: Deploy Cloud Functions

### 3.1 Deploy Morning Check Function

```bash
# Get your project ID
export PROJECT_ID=$(gcloud config get-value project)
echo "Project ID: $PROJECT_ID"

# Redeploy with the missing environment variable
gcloud functions deploy warriors-morning-check \
  --gen2 \
  --runtime=python311 \
  --region=us-west1 \
  --source=/Users/brian/Downloads/files \
  --entry-point=morning_check \
  --trigger-http \
  --allow-unauthenticated \
  --update-env-vars GCP_PROJECT=${PROJECT_ID},FUNCTION_REGION=us-west1 \
  --timeout=120s \
  --memory=256MB
```

### 3.2 Deploy Notification Trigger Function

```bash
# Get your project ID
export PROJECT_ID=$(gcloud config get-value project)
echo "Project ID: $PROJECT_ID"

gcloud functions deploy warriors-notification \
  --gen2 \
  --runtime=python311 \
  --region=us-west1 \
  --source=/Users/brian/Downloads/files \
  --entry-point=trigger_notification \
  --trigger-http \
  --update-env-vars GCP_PROJECT=${PROJECT_ID},FUNCTION_REGION=us-west1 \
  --timeout=60s \
  --memory=256MB
```

**Note**: The notification function doesn't need `--allow-unauthenticated` since it will be called by Cloud Scheduler with proper authentication.

## Step 4: Schedule Daily Morning Check

Create a Cloud Scheduler job to run the morning check daily at 8 AM PT:

```bash
gcloud scheduler jobs create http warriors-daily-check \
  --location=us-west1 \
  --schedule="0 8 * * *" \
  --time-zone="America/Los_Angeles" \
  --uri="https://us-west1-${PROJECT_ID}.cloudfunctions.net/warriors-morning-check" \
  --http-method=POST \
  --oidc-service-account-email="${SERVICE_ACCOUNT}"
```

## Step 5: Verify Deployment

### 5.1 Test Morning Check Manually

```bash
gcloud functions call warriors-morning-check \
  --region=us-west1 \
  --gen2
```

Expected output (no game):
```json
{
  "status": "no_game",
  "message": "No Warriors game scheduled for today"
}
```

Expected output (game found):
```json
{
  "status": "success",
  "game_info": {
    "opponent": "Los Angeles Lakers",
    "game_time": "2026-01-29T19:30:00-08:00",
    "is_home": true
  },
  "notifications_scheduled": {
    "pregame": "2026-01-29T19:15:00-08:00",
    "gametime": "2026-01-29T19:30:00-08:00"
  }
}

# List all tasks to see their names
gcloud tasks list --location=us-west1 --queue=default

# Delete each task individually (replace TASK_ID with the actual task name)
gcloud tasks delete TASK_ID --location=us-west1 --queue=default

# Or, if you want to delete ALL tasks at once, purge the queue:
gcloud tasks queues purge default --location=us-west1
```
## Send test payload for warriors-notification

    "access_token": "MViP8bcl7vktdEAMwpL_uhYgpeQ",
    "expires_in": 604754,
    "refresh_token": "EnxitG01OwiZSo7WPiWL3RJ0tB4",
    "scope": "offline bridge",
    "token_type": "bearer"

# Get credentials
HUE_CLIENT_ID=$(gcloud secrets versions access latest --secret=hue_client_id)
HUE_CLIENT_SECRET=$(gcloud secrets versions access latest --secret=hue_client_secret)
HUE_REFRESH_TOKEN=$(gcloud secrets versions access latest --secret=hue_refresh_token)
HUE_BRIDGE_ID=$(gcloud secrets versions access latest --secret=hue_bridge_id)
HUE_CERT=$(gcloud secrets versions access latest --secret=hue_certificate)

# Create test payload
cat > test_payload.json <<EOF
{
  "notification_type": "gametime",
  "colors": ["#006BB6", "#FDB927"],
  "hue_client_id": "${HUE_CLIENT_ID}",
  "hue_client_secret": "${HUE_CLIENT_SECRET}",
  "hue_refresh_token": "${HUE_REFRESH_TOKEN}",
  "hue_bridge_id": "${HUE_BRIDGE_ID}",
  "hue_cert": $(print -r -- "$HUE_CERT" | jq -Rs .)
}
EOF

# Call the function using gcloud (handles auth automatically)
gcloud functions call warriors-notification \
  --region=us-west1 \
  --gen2 \
  --data="$(cat test_payload.json)"


### 5.2 Check Logs

# List all scheduler jobs with details
gcloud scheduler jobs list --location=us-west1 --filter="name:warriors-" --format="table(name,schedule,nextRunTime,state)"
gcloud tasks list --location=us-west1 --queue=default

```bash
# View morning check logs
gcloud functions logs read warriors-morning-check \
  --region=us-west1 \
  --gen2 \
  --limit=10

# View notification logs
gcloud functions logs read warriors-notification \
  --region=us-west1 \
  --gen2 \
  --limit=10
```

### 5.3 Verify Scheduler Job

```bash
gcloud scheduler jobs list --location=us-west1
```

## Step 6: Monitor and Maintain

### Check Scheduled Jobs

```bash
# List all scheduled Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-west1 | grep warriors
```

### Delete Old Notification Jobs (Optional Cleanup)

After notifications have triggered, Cloud Scheduler jobs remain. You can manually clean them up:

```bash
# List all warriors-related jobs
gcloud scheduler jobs list --location=us-west1 --filter="name:warriors-" --format="value(name)"

# Delete specific job
gcloud scheduler jobs delete "warriors-daily-check" --location=us-west1
```

### Update Secrets (if needed)

```bash
# Update refresh token if it changes
echo -n "new_refresh_token" | gcloud secrets versions add hue_refresh_token --data-file=-
```

## Troubleshooting

### Issue: "Permission denied" errors
**Solution**: Verify service account has Secret Manager access
```bash
./gcloud secrets get-iam-policy hue_client_id
```

### Issue: Function times out
**Solution**: Increase timeout value
```bash
gcloud functions deploy warriors-morning-check \
  --update-env-vars=FUNCTION_REGION=us-west1 \
  --timeout=180s
```

### Issue: Hue API returns 401 Unauthorized
**Solution**: 
1. Refresh token may have expired
2. Generate new refresh token via Postman
3. Update secret:
```bash
echo -n "new_refresh_token" | gcloud secrets versions add hue_refresh_token --data-file=-
```

### Issue: ESPN API returns no games
**Solution**: 
1. Check ESPN API manually: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/9/schedule`
2. Verify Warriors team ID is still "9"
3. Check function logs for error messages

### Issue: Lights don't trigger
**Solution**:
1. Check notification function logs
2. Verify Hue bridge is online
3. Test Hue API manually via Postman
4. Check certificate is valid

## Cost Estimation

Based on 82 Warriors games per season (regular + playoffs):

- **Cloud Functions**: 
  - Morning checks: 365 invocations/year
  - Notifications: ~164 invocations/year (2 per game)
  - **Cost**: ~$0 (well within free tier)

- **Cloud Scheduler**:
  - 1 daily job: 365 runs/year
  - Temporary notification jobs: ~164/year
  - **Cost**: ~$0.10/month (free tier covers 3 jobs)

- **Secret Manager**:
  - 5 secrets, minimal access
  - **Cost**: ~$0.18/month

**Total estimated cost**: ~$0.30/month or **$3.60/year**

## Files Structure

```
warriors-notifier/
├── main.py                  # Main Cloud Function code
├── requirements.txt         # Python dependencies
└── DEPLOYMENT.md           # This file
```

## Next Steps

1. **Test on non-game day**: Verify "no game" response
2. **Test on game day**: Verify notifications are scheduled
3. **Monitor first live notification**: Check if lights trigger correctly
4. **Adjust timing**: Fine-tune 15-minute warning if needed
5. **Customize colors**: Adjust team colors to your preference
6. **Add more teams**: Extend opponent color mapping as needed

## Security Best Practices

- ✅ All credentials stored in Secret Manager (encrypted at rest)
- ✅ Service account with minimal permissions
- ✅ OIDC authentication for Cloud Scheduler
- ✅ HTTPS-only communication
- ⚠️ Consider rotating refresh tokens periodically
- ⚠️ Monitor for unusual API activity

## Support

If you encounter issues:
1. Check Cloud Function logs
2. Verify all secrets are accessible
3. Test Hue API separately via Postman
4. Ensure ESPN API is returning data

Remember: The system is designed to fail gracefully - if there's no game, nothing happens!
