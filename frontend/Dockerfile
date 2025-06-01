# Frontend Dockerfile - Static build only
FROM node:18-alpine as builder

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

# Set build-time environment variables
ARG VITE_API_BASE_URL
ARG VITE_AZURE_CLIENT_ID
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_REDIRECT_URL

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_AZURE_CLIENT_ID=$VITE_AZURE_CLIENT_ID
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
ENV VITE_REDIRECT_URL=$VITE_REDIRECT_URL

# Build the app
RUN npm run build

# List the build output for debugging
RUN ls -la /app/dist

# Create output directory for copying
RUN mkdir -p /output

# Default command - can be overridden in docker-compose
CMD ["sh", "-c", "echo 'Build complete. Files are in /app/dist'"] 