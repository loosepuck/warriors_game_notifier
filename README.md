# Warriors Game Notifier with Philips Hue Lights 🏀💡

Automated home lighting notifications for Golden State Warriors games using Google Cloud Functions and Philips Hue Remote API.

## What It Does

This system automatically:
1. **Checks daily** (8 AM PT) if the Warriors have a game that day
2. **Schedules two notifications** if a game is found:
   - **15 minutes before game**: Lights pulse with opposing team colors
   - **At game time**: Lights flash with Warriors blue and gold

## Features

- ✅ Uses ESPN API for real-time Warriors schedule
- ✅ Supports 30 NBA teams' colors for pre-game notifications
- ✅ OAuth token auto-refresh (won't break after initial setup)
- ✅ Fully serverless (Google Cloud Functions)
- ✅ Runs in Pacific Time zone
- ✅ Minimal cost (~$3.60/year)
- ✅ Secure credential storage (Google Secret Manager)

## Light Patterns

### Pre-Game (15 min before)
- **Effect**: Smooth pulse/breathing
- **Colors**: Opposing team's colors (e.g., Lakers purple & gold)
- **Duration**: ~60 seconds
- **Purpose**: "Hey, game starting soon!"

### Game Time
- **Effect**: Rapid flash
- **Colors**: Warriors blue (#006BB6) and gold (#FDB927)
- **Duration**: ~15 seconds
- **Purpose**: "Game is starting NOW!"

## Project Structure

```
warriors-notifier/
├── main.py              # Cloud Function code
│   ├── ESPNGameChecker  # Fetches Warriors schedule
│   ├── HueAPI          # Controls Philips Hue lights
│   ├── morning_check()  # Daily scheduler entry point
│   └── trigger_notification() # Notification handler
├── requirements.txt     # Python dependencies
├── DEPLOYMENT.md       # Step-by-step deployment guide
├── README.md          # This file
└── TESTING.md         # Testing instructions
```

## How It Works

### Morning Check (8 AM PT Daily)
```
Cloud Scheduler → morning_check() → ESPN API
                      ↓
              Game found today?
                      ↓
                    YES
                      ↓
         Create two Cloud Scheduler jobs:
         1. Pre-game notification (game_time - 15 min)
         2. Game-time notification (game_time)
```

### Notification Trigger (Scheduled Times)
```
Cloud Scheduler → trigger_notification() → Hue Remote API
                                              ↓
                                    Control lights via OAuth
                                              ↓
                                    Pulse or flash colors
```

## Architecture Decisions

### Why Google Cloud Functions?
- **Serverless**: No always-on infrastructure needed
- **Cost-effective**: Free tier covers most usage
- **Reliable**: Managed service with automatic scaling
- **Regional**: Deploy in us-west1 (close to PT timezone)

### Why Cloud Scheduler over cron?
- **Managed**: No need to maintain a server
- **Timezone-aware**: Native PT support
- **Integrated**: Works seamlessly with Cloud Functions
- **Dynamic**: Can create/delete jobs programmatically

### Why Remote API over Local Bridge API?
- **Cloud-compatible**: Works from Google Cloud
- **No VPN needed**: No complex networking
- **OAuth standard**: Secure token-based auth
- **Trade-off**: Slightly higher latency (~200ms), but acceptable for this use case

## Customization Options

### Adjust Notification Timing
In `main.py`, change:
```python
pregame_time = game_time - timedelta(minutes=15)  # Change 15 to your preference
```

### Customize Light Effects
Modify in `HueAPI` class:
```python
def pulse_colors(self, colors, duration_seconds=60):  # Adjust duration
    # Modify transition time, brightness, etc.
    
def flash_colors(self, colors, flash_count=5):  # Change flash count
    # Adjust flash pattern
```

### Add More Team Colors
In `TEAM_COLORS` dict, add:
```python
'Team Name': {'primary': '#HEX1', 'secondary': '#HEX2'}
```

### Change Schedule Time
Update Cloud Scheduler job:
```bash
gcloud scheduler jobs update http warriors-daily-check \
  --schedule="0 7 * * *"  # Change to 7 AM
```

## Requirements

### Google Cloud
- GCP project with billing enabled
- APIs enabled: Cloud Functions, Scheduler, Secret Manager
- `gcloud` CLI configured

### Philips Hue
- Hue Bridge (any generation)
- Hue developer account
- OAuth credentials (Client ID, Secret, Refresh Token)
- Bridge ID
- API certificate

### Development
- Python 3.11+
- Basic understanding of OAuth 2.0
- Familiarity with REST APIs

## Quick Start

1. **Complete Hue setup** (see Postman testing)
2. **Clone/download** these files
3. **Follow DEPLOYMENT.md** step-by-step
4. **Test** using TESTING.md
5. **Enjoy** automated game notifications!

## Known Limitations

1. **Single notification per event type**: Currently triggers all lights the same way
2. **No granular light control**: All lights flash/pulse together
3. **Basic color transitions**: Uses Hue's built-in effects
4. **No game outcome integration**: Only start-time notifications
5. **Requires internet**: Both ends (GCP and Hue Bridge) need connectivity

## Future Enhancements (Ideas)

- [ ] Per-room light configurations
- [ ] Different patterns for home vs. away games
- [ ] Playoff-specific effects (more intense!)
- [ ] Score updates during game (requires real-time feed)
- [ ] Multiple team support (if you follow other teams)
- [ ] SMS/email backup notifications
- [ ] Game outcome celebration (post-game API check)
- [ ] Integration with TV power (IFTTT?)

## Troubleshooting Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| No notification triggered | Check Cloud Scheduler logs |
| Lights don't respond | Verify Hue bridge online, test via Postman |
| "No game" on game day | Check ESPN API manually |
| OAuth errors | Refresh token in Postman, update secret |
| Wrong timezone | Verify Cloud Scheduler timezone setting |
| Function timeout | Increase timeout in deployment |

## Cost Breakdown

Assumes 82 games/season (regular + playoffs):

| Service | Usage | Monthly Cost | Annual Cost |
|---------|-------|--------------|-------------|
| Cloud Functions | ~45 invocations/month | $0.00 | $0.00 |
| Cloud Scheduler | 1 daily + ~14 game jobs | $0.10 | $1.20 |
| Secret Manager | 5 secrets, minimal access | $0.18 | $2.16 |
| Cloud Build | Function deployments | $0.03 | $0.36 |
| **Total** | | **~$0.31** | **~$3.72** |

*All services have generous free tiers that cover most of this usage*

## Privacy & Security

- ✅ All credentials encrypted at rest (Secret Manager)
- ✅ HTTPS-only communication
- ✅ No data stored long-term
- ✅ Minimal permissions (least privilege)
- ✅ No third-party access
- ℹ️ ESPN API: Public data, no authentication
- ℹ️ Hue API: Your OAuth tokens, your bridge

## Credits

- **NBA Schedule Data**: ESPN API
- **Smart Home Control**: Philips Hue Remote API
- **Cloud Infrastructure**: Google Cloud Platform
- **Inspiration**: The beautiful game of basketball 🏀

## License

This is a personal project for educational purposes. Use freely!

---

**Go Warriors!** 🏀💙💛
