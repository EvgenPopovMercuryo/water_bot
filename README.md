# Water Bot

Telegram bot for tracking daily water intake. Built with Python and python-telegram-bot.

## Features

- Track daily water intake
- View daily and weekly statistics
- Set up custom reminders
- Easy-to-use interface with quick buttons

## Environment Variables

The following environment variables are required:

- `TELEGRAM_TOKEN`: Your Telegram bot token from BotFather

## Deployment

This bot is configured for deployment on Render.com as a worker service.

### Database

The bot uses SQLite database which is stored in the `/data` directory on Render. 