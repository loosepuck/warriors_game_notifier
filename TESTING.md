# Testing Guide - Warriors Game Notifier

This guide helps you test the system thoroughly before relying on it for live game notifications.

## Pre-Deployment Testing (Local)

### Test 1: Verify ESPN API Access

```bash
# Test Warriors schedule endpoint
curl "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/9/schedule" | python3 -m json.tool | less

# Look for:
# - "events" array with game data
# - "date" field for each game
# - "competitors" with team info
```

**Expected**: JSON response with Warriors schedule

### Test 2: Validate Hue API via Postman

Before deploying, confirm your Hue setup works:

1. **Get Access Token** (using refresh token)
   - Method: POST
   - URL: `https://api.meethue.com/v2/oauth2/token`
   - Body (x-www-form-urlencoded):
     - `grant_type`: `refresh_token`
     - `refresh_token`: `<your_refresh_token>`
     - `client_id`: `<your_client_id>`
     - `client_secret`: `<your_client_secret>`

2. **List Lights**
   - Method: GET
   - URL: `https://api.meethue.com/route/api/<bridge_id>/lights`
   - Headers:
     - `Authorization`: `Bearer <access_token>`

3. **Test Light Control**
   - Method: PUT
   - URL: `https://api.meethue.com/route/api/<bridge_id>/lights/1/state`
   - Headers:
     - `Authorization`: `Bearer <access_token>`
     - `Content-Type`: `application/json`
   - Body (raw JSON):
     ```json
     {
       "on": true,
       "xy": [0.3, 0.3],
       "bri": 254
     }
     ```

**Expected**: Lights should change color/brightness

### Test 3: Color Conversion Verification

Test the hex-to-xy color conversion:

```python
from main import HueAPI

hue = HueAPI('dummy', 'dummy', 'dummy', 'dummy')

# Test Warriors blue
warriors_blue_xy = hue.hex_to_xy('#006BB6')
print(f"Warriors Blue XY: {warriors_blue_xy}")  # Should be around [0.15, 0.05]

# Test Warriors gold
warriors_gold_xy = hue.hex_to_xy('#FDB927')
print(f"Warriors Gold XY: {warriors_gold_xy}")  # Should be around [0.50, 0.47]
```

## Post-Deployment Testing

### Test 4: Manual Function Invocation

After deploying to Google Cloud:

```bash
# Test morning check function
gcloud functions call warriors-morning-check \
  --region=us-west1 \
  --gen2

# Check logs
gcloud functions logs read warriors-morning-check \
  --region=us-west1 \
  --gen2 \
  --limit=20
```

**Expected Output (No Game)**:
```json
{
  "result": "{\"status\": \"no_game\", \"message\": \"No Warriors game scheduled for today\"}"
}
```

**Expected Output (Game Day)**:
```json
{
  "result": "{\"status\": \"success\", \"game_info\": {...}, \"notifications_scheduled\": {...}}"
}
```

### Test 5: Simulate Game Day (Manual Trigger)

To test without waiting for an actual game:

**Option A: Modify Code Temporarily**
1. Edit `main.py` in `ESPNGameChecker.get_todays_game()`
2. Change the date logic to return a fake game:
```python
# Temporary: Always return a game in 30 minutes for testing
game_time = datetime.now(pytz.timezone('America/Los_Angeles')) + timedelta(minutes=30)
return {
    'game_time': game_time,
    'opponent': 'Los Angeles Lakers',
    'is_home_game': True,
    'event_name': 'TEST: Warriors vs Lakers'
}
```
3. Redeploy function
4. Call manually
5. Check if notifications are scheduled

**Option B: Direct Notification Test**
Skip the morning check and test notifications directly:

```bash
# Create a test payload
cat > test_payload.json << EOF
{
  "notification_type": "gametime",
  "colors": ["#006BB6", "#FDB927"],
  "hue_client_id": "$(gcloud secrets versions access latest --secret=hue_client_id)",
  "hue_client_secret": "$(gcloud secrets versions access latest --secret=hue_client_secret)",
  "hue_refresh_token": "$(gcloud secrets versions access latest --secret=hue_refresh_token)",
  "hue_bridge_id": "$(gcloud secrets versions access latest --secret=hue_bridge_id)",
  "hue_cert": "$(gcloud secrets versions access latest --secret=hue_certificate)"
}
EOF

# Call notification function
gcloud functions call warriors-notification \
  --region=us-west1 \
  --gen2 \
  --data="$(cat test_payload.json)"
```

**Expected**: Your lights should flash Warriors colors immediately!

### Test 6: Verify Cloud Scheduler Jobs

On a game day, check if notification jobs were created:

```bash
# List all Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-west1

# Look for jobs like:
# warriors-pregame-20260129-1915
# warriors-gametime-20260129-1930
```

### Test 7: Check Scheduled Job Execution

Wait for the scheduled time and monitor:

```bash
# Follow logs in real-time
gcloud functions logs read warriors-notification \
  --region=us-west1 \
  --gen2 \
  --limit=50 \
  --format="table(time, log)"

# Or check scheduler job history
gcloud scheduler jobs describe warriors-pregame-YYYYMMDD-HHMM \
  --location=us-west1
```

**Expected**: Logs showing "Triggering pre-game pulse notification" or "Triggering game-time flash notification"

## Integration Testing Scenarios

### Scenario 1: Full Game Day Flow

**Setup**: Find a day with a Warriors game (check ESPN.com)

**Test Steps**:
1. Wait for 8 AM PT or trigger manually
2. Verify morning check detects the game
3. Verify two Cloud Scheduler jobs are created
4. Wait for pre-game notification (15 min before)
5. Observe lights pulsing with opponent colors
6. Wait for game-time notification
7. Observe lights flashing Warriors colors

**Success Criteria**:
- ✅ Game detected correctly
- ✅ Opponent identified
- ✅ Home/away status correct
- ✅ Both notifications triggered on time
- ✅ Light patterns distinct and noticeable

### Scenario 2: No Game Day

**Setup**: Pick a day with no Warriors game

**Test Steps**:
1. Trigger morning check manually or wait for 8 AM PT
2. Verify response indicates no game
3. Verify no notification jobs created
4. Verify no lights triggered

**Success Criteria**:
- ✅ Returns "no_game" status
- ✅ No scheduler jobs created
- ✅ No errors in logs

### Scenario 3: Back-to-Back Games

**Setup**: Find consecutive game days

**Test Steps**:
1. Day 1: Verify first game's notifications work
2. Day 2: Verify second game's notifications work
3. Check that Day 1 jobs don't interfere with Day 2

**Success Criteria**:
- ✅ Each game gets its own notification jobs
- ✅ No job conflicts
- ✅ Previous day's jobs can coexist

### Scenario 4: OAuth Token Refresh

**Setup**: Wait 1+ hour after initial deployment

**Test Steps**:
1. Trigger a notification (access token should be expired)
2. Monitor logs for token refresh
3. Verify notification still succeeds

**Success Criteria**:
- ✅ Function automatically refreshes token
- ✅ No authentication errors
- ✅ Lights trigger successfully

## Monitoring & Validation

### Daily Health Checks

```bash
# Check if daily scheduler is running
gcloud scheduler jobs describe warriors-daily-check \
  --location=us-west1 \
  --format="value(state, schedule)"

# Should show: ENABLED, "0 8 * * *"
```

### Weekly Validation

```bash
# Review last 7 days of morning checks
gcloud functions logs read warriors-morning-check \
  --region=us-west1 \
  --gen2 \
  --limit=200 \
  --format="table(time, log)" \
  --filter="timestamp>=\"$(date -d '7 days ago' --iso-8601)\""
```

### Monthly Review

- Check Secret Manager access logs
- Verify no unusual API access patterns
- Review Cloud Functions metrics:
  ```bash
  gcloud functions describe warriors-morning-check \
    --region=us-west1 \
    --gen2 \
    --format="value(serviceConfig.availableMemory, serviceConfig.timeoutSeconds)"
  ```

## Common Test Failures & Solutions

### Failure: "Permission denied" accessing secrets

**Cause**: Service account lacks Secret Manager permissions

**Solution**:
```bash
export PROJECT_ID="your-project-id"
export SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"

gcloud secrets add-iam-policy-binding hue_client_id \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

### Failure: ESPN API returns empty events

**Cause**: Either no games scheduled OR Warriors team ID changed

**Solution**:
1. Check manually: https://www.espn.com/nba/team/schedule/_/name/gs
2. Verify team ID in API response
3. Update `WARRIORS_TEAM_ID` in `main.py` if needed

### Failure: Hue lights don't respond

**Cause**: Multiple possibilities
- Bridge offline
- OAuth token expired and refresh failed
- Certificate issue

**Solution**:
1. Check bridge in Hue app
2. Test API via Postman
3. Verify certificate in Secret Manager matches current cert
4. Check function logs for specific error

### Failure: Notification triggered at wrong time

**Cause**: Timezone mismatch

**Solution**:
```bash
# Verify scheduler timezone
gcloud scheduler jobs describe warriors-daily-check \
  --location=us-west1 \
  --format="value(timeZone)"

# Should be: America/Los_Angeles

# Update if needed
gcloud scheduler jobs update http warriors-daily-check \
  --location=us-west1 \
  --time-zone="America/Los_Angeles"
```

## Performance Benchmarks

Expected execution times:

| Function | Typical Duration | Max Expected |
|----------|-----------------|--------------|
| morning_check (no game) | 1-2 seconds | 5 seconds |
| morning_check (game found) | 3-5 seconds | 10 seconds |
| trigger_notification | 2-4 seconds | 10 seconds |

If exceeding max expected, investigate:
- Network latency
- API rate limiting
- Secret Manager access time

## Test Checklist

Before considering the system production-ready:

- [ ] ESPN API access verified
- [ ] Hue API access via Postman confirmed
- [ ] All secrets stored in Secret Manager
- [ ] Morning check function deployed successfully
- [ ] Notification function deployed successfully
- [ ] Daily scheduler created and enabled
- [ ] Manual morning check invocation works
- [ ] Manual notification trigger works
- [ ] Tested on actual game day (pre-game notification)
- [ ] Tested on actual game day (game-time notification)
- [ ] Tested on non-game day (no false triggers)
- [ ] OAuth token refresh verified working
- [ ] Logs accessible and readable
- [ ] Error handling tested (e.g., API down)
- [ ] Cost monitoring set up
- [ ] Documentation reviewed

## Debugging Tools

### Enable Verbose Logging

Add to `main.py` for more detailed logs:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test Specific Functions Locally

```python
# Test ESPN API locally
from main import ESPNGameChecker

game = ESPNGameChecker.get_todays_game()
print(json.dumps(game, indent=2, default=str))
```

### Monitor in Real-Time

```bash
# Stream logs live
gcloud functions logs tail warriors-morning-check \
  --region=us-west1 \
  --gen2
```

## Success Metrics

Your system is working correctly when:
1. ✅ No errors in logs for 7+ consecutive days
2. ✅ 100% of games detected correctly
3. ✅ All notifications trigger within 1 minute of scheduled time
4. ✅ OAuth tokens refresh automatically without manual intervention
5. ✅ No duplicate notifications
6. ✅ Lights return to normal state after notifications

---

**Ready for Live Games!** 🎉

Once all tests pass, your system is ready to notify you about every Warriors game automatically. Sit back and enjoy the show! 🏀
