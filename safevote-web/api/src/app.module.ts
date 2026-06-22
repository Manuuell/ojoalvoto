import { Module } from '@nestjs/common';
import { ActasModule } from './actas/actas.module';

@Module({
  imports: [ActasModule],
})
export class AppModule {}
