import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors(); // el frontend Next.js consume esta API
  const port = process.env.PORT || 8000;
  await app.listen(port);
  console.log(`SafeVote API escuchando en :${port}`);
}
bootstrap();
