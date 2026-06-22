import { Body, Controller, Get, Param, Post, Query, Res } from '@nestjs/common';
import { Response } from 'express';
import { ActasService } from './actas.service';

@Controller('api')
export class ActasController {
  constructor(private svc: ActasService) {}

  @Get('actas/next')
  next(@Query('labeler') labeler = 'anon') {
    return this.svc.next(labeler.slice(0, 40));
  }

  @Get('actas/:id/pdf')
  async pdf(@Param('id') id: string, @Res() res: Response) {
    const buf = await this.svc.getPdf(id);
    if (!buf) return res.status(404).send('no encontrada');
    res.set({ 'Content-Type': 'application/pdf', 'Cache-Control': 'public, max-age=86400' });
    res.send(buf);
  }

  @Post('actas/:id/submit')
  submit(@Param('id') id: string, @Body() b: any) {
    return this.svc.submit(id, (b.labeler || 'anon').slice(0, 40), b.votes || {});
  }

  @Post('actas/:id/flag')
  flag(@Param('id') id: string, @Body() b: any) {
    return this.svc.flag(id, (b.labeler || 'anon').slice(0, 40), b.votes || {}, (b.nota || '').slice(0, 300));
  }

  @Post('actas/:id/skip')
  skip(@Param('id') id: string) {
    return this.svc.skip(id);
  }

  @Get('stats')
  stats() {
    return this.svc.stats();
  }

  @Get('flagged')
  flagged() {
    return this.svc.flagged();
  }

  @Get('leaderboard')
  leaderboard() {
    return this.svc.leaderboard();
  }

  @Get('elecciones')
  elecciones() {
    return this.svc.elecciones();
  }

  @Get('health')
  health() {
    return { ok: true };
  }
}
