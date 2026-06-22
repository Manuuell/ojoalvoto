FROM node:20-slim

# OpenSSL para Prisma
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY prisma ./prisma
RUN npx prisma generate
COPY . .
RUN npm run build

EXPOSE 8000
# Al arrancar: aplica el esquema, carga el manifest si está vacío y levanta la API
CMD npx prisma db push --skip-generate && npx ts-node src/seed.ts; node dist/main
