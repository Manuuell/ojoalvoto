import { Module } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { ActasController } from './actas.controller';
import { ActasService } from './actas.service';

@Module({
  controllers: [ActasController],
  providers: [ActasService, PrismaService],
})
export class ActasModule {}
