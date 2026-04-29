FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

RUN npm run build

EXPOSE 3000
ENV HOSTNAME="0.0.0.0"

CMD ["npm", "start"]
