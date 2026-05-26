FROM node:26-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

COPY src/ ./src/

EXPOSE 3000
ENV NODE_ENV=production

CMD ["node", "src/server.js"]
