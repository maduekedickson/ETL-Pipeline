#!/bin/bash
# ==============================================================================
# RiteClick ETL Web Application - EC2 Automated Deployment Script
# Operating System: Amazon Linux 2023 or Ubuntu 22.04 LTS
# ==============================================================================
set -e

echo "=== [1/6] Updating System Packages & Installing Dependencies ==="
if command -v dnf &> /dev/null; then
    # Amazon Linux 2023 / RHEL
    sudo dnf update -y
    sudo dnf install -y python3.11 python3.11-pip git nginx openssl
    PYTHON_BIN="python3.11"
elif command -v apt-get &> /dev/null; then
    # Ubuntu / Debian
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv git nginx openssl
    PYTHON_BIN="python3"
else
    echo "Unsupported package manager."
    exit 1
fi

APP_DIR="/opt/riteclick"
echo "=== [2/6] Setting Up Application Directory: $APP_DIR ==="
sudo mkdir -p $APP_DIR
sudo mkdir -p /var/log/riteclick
sudo chown -R $USER:$USER $APP_DIR
sudo chown -R $USER:$USER /var/log/riteclick

# Copy project files if running inside git repo
if [ -f "requirements.txt" ]; then
    cp -r * $APP_DIR/
fi

cd $APP_DIR

echo "=== [3/6] Configuring Python Virtual Environment ==="
$PYTHON_BIN -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Ensure .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    # Generate random secret key
    SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change-this-to-a-secure-random-32-byte-hex-string/$SECRET_KEY/" .env
fi

echo "=== [4/6] Generating Self-Signed SSL Certificate (for HTTPS) ==="
sudo mkdir -p /etc/ssl/certs /etc/ssl/private
if [ ! -f "/etc/ssl/certs/riteclick.crt" ]; then
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/private/riteclick.key \
        -out /etc/ssl/certs/riteclick.crt \
        -subj "/C=US/ST=Cloud/L=Seattle/O=RiteClick/OU=DataPlatform/CN=localhost"
    echo "SSL Certificate generated at /etc/ssl/certs/riteclick.crt"
fi

echo "=== [5/6] Configuring Nginx Reverse Proxy ==="
if [ -d "/etc/nginx/conf.d" ]; then
    sudo cp deployment/nginx.conf /etc/nginx/conf.d/riteclick.conf
    # Remove default welcome if present
    sudo rm -f /etc/nginx/conf.d/default.conf
else
    sudo cp deployment/nginx.conf /etc/nginx/sites-available/riteclick
    sudo ln -sf /etc/nginx/sites-available/riteclick /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
fi

sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "=== [6/6] Configuring & Starting Gunicorn Systemd Service ==="
sudo cp deployment/riteclick.service /etc/systemd/system/riteclick.service
# Update user in systemd service to current user
sudo sed -i "s/User=ec2-user/User=$USER/g" /etc/systemd/system/riteclick.service
sudo sed -i "s/Group=ec2-user/Group=$USER/g" /etc/systemd/system/riteclick.service

sudo systemctl daemon-reload
sudo systemctl enable riteclick
sudo systemctl restart riteclick

echo "==================================================================="
echo " RiteClick ETL Web App Deployed Successfully!                      "
echo " Access via HTTPS at: https://<YOUR_EC2_PUBLIC_IP_OR_DOMAIN>      "
echo " Status Check: sudo systemctl status riteclick                    "
echo " Nginx Status: sudo systemctl status nginx                        "
echo "==================================================================="
