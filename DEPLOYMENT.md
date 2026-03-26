# Warriors Game Notifier - Google Cloud Deployment Guide

## Overview
Complete deployment guide for the Warriors game notification system using Google Cloud Functions and Philips Hue lights.

## Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed and authenticated
- Philips Hue Bridge with internet access
- Philips Hue developer account with OAuth credentials
- zsh shell (macOS default)

---

## Part 1: Philips Hue Setup

### 1.1 Create Hue Developer Account
1. Go to https://developers.meethue.com/
2. Register and verify your email
3. Log in to the developer portal

### 1.2 Register Your Application
1. Navigate to "My Apps" → "Create New App"
2. Fill in application details:
   - **App Name**: `Warriors Game Notifier` (or your choice)
   - **Description**: `Home automation for Warriors game notifications`
   - **Callback URL**: `https://localhost:8080/callback`
3. Save your **Client ID** and **Client Secret** (keep these secure!)

### 1.3 Get OAuth Tokens via Browser & Postman

**Step 1: Get Authorization Code (Browser)**

Construct this URL (replace `YOUR_CLIENT_ID`):

https://api.meethue.com/v2/oauth2/authorize?client_id=2438f520-5cdc-4e07-a0ee-6991e6513c8c&response_type=code&state=GetCode&redirect_uri=https://localhost:8080/callback


1. Open URL in browser
2. Log in and authorize the app
3. You'll be redirected to `https://localhost:8080/callback?code=VYHuNzI`
4. **Copy the authorization code** from the URL (the `code=` parameter)

**Step 2: Exchange Code for Tokens (Postman)**

1. Open Postman
2. Import the Hue certificate:
   - Settings → Certificates → Add Certificate
   - Host: `api.meethue.com`
   - Upload the `.pem` file from Philips documentation

3. Create new POST request:
   - Method: `POST`
   - URL: `https://api.meethue.com/v2/oauth2/token`
   - Headers: `Content-Type: application/x-www-form-urlencoded`
   - Body (x-www-form-urlencoded):
     - `grant_type`: `authorization_code`
     - `code`: `-o38tmz`
     - `client_id`: `2438f520-5cdc-4e07-a0ee-6991e6513c8c`
     - `client_secret`: `9bf0d60a7d905c8e94c5c03ab73454b0`
     - `redirect_uri`: `https://localhost:8080/callback`

4. Send request
5. **Save the response:**
   - `access_token` (temporary, ~1 hour)
   - `refresh_token` (long-lived - **THIS IS WHAT YOU NEED!**)

### 1.4 Link Your App to the Bridge

1. Press the **physical link button** on your Hue Bridge
2. Within 30 seconds, make this request in Postman:
   - Method: `POST`
   - URL: `https://api.meethue.com/route/api`
   - Headers: `Authorization: Bearer YOUR_ACCESS_TOKEN`
   - Body (raw JSON):
     ```json
     {
       "devicetype": "warriors_notifier#gcf"
     }
     ```

3. **Save the response:**
   - The `username` field is your **Bridge ID**

### 1.5 Save Your Credentials

You now have everything you need:
- ✅ Client ID - 2438f520-5cdc-4e07-a0ee-6991e6513c8c
- ✅ Client Secret - 9bf0d60a7d905c8e94c5c03ab73454b0
- ✅ Refresh Token - QnQP2YRTVy66J6JUDhXxS_dVMtU
- ✅ Bridge ID - jahhW0iyuXXPPvff42BB1mfkCN64AER5DyO5jCVZ
- ✅ Certificate (.pem file) - /Users/brian/Desktop/hue1.pem

---

## Part 2: Google Cloud Setup

### 2.1 Set Your Project ID

export PROJECT_ID="warriors-game-notifier"
gcloud config set project $PROJECT_ID

### 2.2 Enable Required APIs

gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com

### 2.3 Store Secrets in Secret Manager

# Create all secrets (replace with your actual values)
echo -n "2438f520-5cdc-4e07-a0ee-6991e6513c8c" | gcloud secrets create hue_client_id --data-file=-
echo -n "9bf0d60a7d905c8e94c5c03ab73454b0" | gcloud secrets create hue_client_secret --data-file=-
echo -n "QnQP2YRTVy66J6JUDhXxS_dVMtU" | gcloud secrets create hue_refresh_token --data-file=-
echo -n "jahhW0iyuXXPPvff42BB1mfkCN64AER5DyO5jCVZ" | gcloud secrets create hue_bridge_id --data-file=-

# Store the certificate
gcloud secrets create hue_certificate --data-file=/Users/brian/Desktop/hue1.pem

### 2.4 Grant Secret Access to Cloud Functions

# Get the default compute service account
export SERVICE_ACCOUNT="9010317804-compute@developer.gserviceaccount.com"

# Grant access to all secrets
for secret in hue_client_id hue_client_secret hue_refresh_token hue_bridge_id hue_certificate; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"
done

### 2.5 Grant Cloud Tasks Permissions

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/cloudtasks.enqueuer"

### 2.6 Create Cloud Tasks Queue

gcloud tasks queues create default --location=us-west1

---

## Part 3: Deploy Cloud Functions

### 3.1 Prepare Your Code

# Make sure you have these files in your project directory:
# `main.py`
# `requirements.txt`

# Navigate to your project directory:

cd /Users/brian/Downloads/files

### 3.2 Deploy Morning Check Function

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

### 3.3 Deploy Notification Function

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

**Note:** Notification function does NOT use `--allow-unauthenticated` (called by Cloud Tasks with auth)

---

## Part 4: Schedule Daily Check

### 4.1 Create Daily Scheduler Job

gcloud scheduler jobs create http warriors-daily-check \
  --location=us-west1 \
  --schedule="0 8 * * *" \
  --time-zone="America/Los_Angeles" \
  --uri="https://us-west1-${PROJECT_ID}.cloudfunctions.net/warriors-morning-check" \
  --http-method=POST \
  --oidc-service-account-email="${SERVICE_ACCOUNT}"

# This runs every day at 8:00 AM Pacific Time.

# ---

## Part 5: Testing

### 5.1 Test Morning Check Manually

gcloud functions call warriors-morning-check \
  --region=us-west1 \
  --gen2

**Expected output (no game):**
```json
{
  "result": "{\"status\": \"no_game\", \"message\": \"No Warriors game scheduled for today\"}"
}
```

**Expected output (game found):**
```json
{
  "result": "{\"status\": \"success\", \"game_info\": {...}, \"notifications_scheduled\": {...}}"
}
```

### 5.2 Check Logs

# Morning check logs
gcloud functions logs read warriors-morning-check \
  --region=us-west1 \
  --gen2 \
  --limit=20

# Notification logs
gcloud functions logs read warriors-notification \
  --region=us-west1 \
  --gen2 \
  --limit=20

### 5.3 Test Notification Function Manually

Create a test payload:

# Get credentials from Secret Manager
HUE_CLIENT_ID=$(gcloud secrets versions access latest --secret=hue_client_id)
HUE_CLIENT_SECRET=$(gcloud secrets versions access latest --secret=hue_client_secret)
HUE_REFRESH_TOKEN=$(gcloud secrets versions access latest --secret=hue_refresh_token)
HUE_BRIDGE_ID=$(gcloud secrets versions access latest --secret=hue_bridge_id)
HUE_CERT=$(gcloud secrets versions access latest --secret=hue_certificate)

# Create test payload file
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

# Trigger the function
gcloud functions call warriors-notification \
  --region=us-west1 \
  --gen2 \
  --data="$(cat test_payload.json)"

**Your lights should flash Warriors blue and gold, then restore to original state!**

### 5.4 Check Scheduled Tasks

# View tasks in the queue
gcloud tasks list --location=us-west1 --queue=default

# Purge all tasks (if needed for cleanup)
gcloud tasks queues purge default --location=us-west1

### 5.5 Check Scheduler Jobs

gcloud scheduler jobs list --location=us-west1

---

## Maintenance

### Update Refresh Token

If your Hue refresh token expires or gets revoked:

# Get new token via Postman (see Part 1)
# Then update the secret:
echo -n "chfYLnnkRqfzJxkbGe_c4Hy3qzw" | gcloud secrets versions add hue_refresh_token --data-file=-

### Update Certificate

When Philips rotates their SSL certificate:

gcloud secrets versions add hue_certificate --data-file=/Users/brian/Desktop/hue2.pem

### View Function Status

gcloud functions describe warriors-morning-check \
  --region=us-west1 \
  --gen2 \
  --format="value(state,updateTime)"

### Redeploy After Code Changes

# Navigate to project directory
cd /Users/brian/Downloads/files

# Redeploy both functions
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

---

## Troubleshooting

### Issue: 400 Invalid resource field value in the request. [reason: "RESOURCE_PROJECT_INVALID"]

**Solution:** Set shell variable PROJECT_ID and redeploy morning-check function:
# Before any deployment, verify:
echo $PROJECT_ID          # Should show: warriors-game-notifier

# If null, restore it:
export PROJECT_ID="warriors-game-notifier"

# Or add to ~/.zshrc for permanent availability:
echo 'export PROJECT_ID="warriors-game-notifier"' >> ~/.zshrc
source ~/.zshrc

# Redeploy morning-check function
gcloud functions deploy warriors-morning-check \
  --gen2 \
  --runtime=python311 \
  --region=us-west1 \
  --source=. \
  --entry-point=morning_check \
  --trigger-http \
  --allow-unauthenticated \
  --update-env-vars GCP_PROJECT=${PROJECT_ID},FUNCTION_REGION=us-west1 \
  --timeout=120s \
  --memory=256MB

### Issue: "Permission denied" on secrets

**Solution:** Re-grant access to compute service account:
export SERVICE_ACCOUNT="9010317804-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding hue_refresh_token \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

### Issue: Tasks failing with 500 error

**Solution:** Check notification function logs for specific error:
gcloud functions logs read warriors-notification \
  --region=us-west1 \
  --gen2 \
  --limit=50

Common causes:
- Invalid refresh token (regenerate via Postman)
- Certificate issues (code has SSL fallback)
- Hue bridge offline

### Issue: No tasks created on game day

**Solution:** Check morning-check logs:
gcloud functions logs read warriors-morning-check \
  --region=us-west1 \
  --gen2 \
  --limit=50

Verify game was detected and tasks were scheduled.

### Issue: Refresh token expired

**Symptoms:** Notification fails with OAuth errors

**Solution:**
1. Get new authorization code (browser)
2. Exchange for new tokens (Postman)
3. Update secret:
   echo -n "aM4_My9FlVV4YNS_wIuoBnY2efU" | gcloud secrets versions add hue_refresh_token --data-file=-

---

## Cost Estimate

Based on 82 Warriors games per season:

| Service | Monthly Cost | Annual Cost |
|---------|--------------|-------------|
| Cloud Functions | $0.00 | $0.00 |
| Cloud Tasks | $0.10 | $1.20 |
| Secret Manager | $0.18 | $2.16 |
| Cloud Build | $0.03 | $0.36 |
| **Total** | **~$0.31** | **~$3.72** |

Most usage is covered by Google Cloud's free tier.

---

## Success Checklist

- [ ] Philips Hue developer account created
- [ ] OAuth credentials obtained (Client ID, Secret, Refresh Token, Bridge ID)
- [ ] Certificate downloaded and saved
- [ ] Google Cloud project created with billing
- [ ] All APIs enabled
- [ ] All secrets stored in Secret Manager
- [ ] Service account permissions granted
- [ ] Cloud Tasks queue created
- [ ] Both Cloud Functions deployed successfully
- [ ] Daily scheduler created
- [ ] Manual test successful (lights flash and restore)
- [ ] Morning check returns correct status

---

**Your automation is ready!** 🎉

The system will automatically detect Warriors games every morning at 8 AM PT and flash your lights with team colors at game time.

**Go Warriors!** 🏀💙💛
