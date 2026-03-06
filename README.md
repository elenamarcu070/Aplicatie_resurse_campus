<img width="1910" height="920" alt="image" src="https://github.com/user-attachments/assets/bdd97cfd-526f-48be-a796-a1067772e317" /># Campus Resources Reservation System

Web application built with Django that allows students to reserve shared campus resources such as washing machines.

The system manages reservations, schedules, dormitory administrators and provides a calendar interface for booking available time slots.

## Features

- Google authentication
- Reservation calendar for washing machines
- Dormitory-based access control
- Admin management for machines and schedules
- Automatic cancellation when machines are disabled
- Student phone number integration
- WhatsApp notifications via Twilio

## Tech Stack

- Python
- Django
- PostgreSQL
- Django Allauth (Google login)
- Twilio API
- HTML / CSS / JavaScript

## Architecture

Student → Django Backend → PostgreSQL Database → Notification API (Twilio)

## Screenshots

<img width="1910" height="920" alt="image" src="https://github.com/user-attachments/assets/998e3664-1cc9-4514-8df2-71b7d5ba8ee3" />
<img width="1907" height="907" alt="image" src="https://github.com/user-attachments/assets/39cc55de-919f-4371-a53d-251e2c2e7310" />


## Installation

```bash
git clone ...
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver


## Deployment
The application is deployed and currently used in university dormitories.
Hosted on Railway with PostgreSQL database.
Domain: washtuiasi.ro
