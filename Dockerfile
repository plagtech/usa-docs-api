FROM node:20-slim

# Install Python 3 and pip
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

# Install Node dependencies
COPY package.json .
RUN npm install --production

# Copy app code
COPY . .

# Create temp and forms cache directories
RUN mkdir -p tmp pdf-engine/forms

EXPOSE 3000

CMD ["node", "server.js"]
