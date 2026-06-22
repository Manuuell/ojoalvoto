import { Injectable } from '@nestjs/common';
import axios from 'axios';
import { existsSync, readFileSync, mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';
import { PrismaService } from '../prisma/prisma.service';

const LOCK_TTL_MIN = 15;
const PDFS_DIR = process.env.PDFS_DIR || '/data/pdfs';
const CACHE_DIR = process.env.CACHE_DIR || '/data/cache';
const REG_BASE =
  'https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf';

// Resultados oficiales (preconteo Registraduría, 31-may-2026) — fuente para Estadísticas
const OFICIAL = {
  fecha: 'Preconteo · 31 de mayo de 2026',
  censo: 41421973, votantes: 23978304, participacion: 57.89,
  validos: 23685329, nulos: 245389, noMarcadas: 47586, blancos: 406970,
  candidatos: [
    { nombre: 'Abelardo de la Espriella', votos: 10361499, pct: 44.51 },
    { nombre: 'Iván Cepeda Castro', votos: 9688361, pct: 41.62 },
    { nombre: 'Paloma Valencia', votos: 1639685, pct: 7.04 },
    { nombre: 'Sergio Fajardo', votos: 1009073, pct: 4.33 },
    { nombre: 'Claudia López', votos: 225517, pct: 0.97 },
    { nombre: 'Raúl Botero Jaramillo', votos: 206140, pct: 0.89 },
    { nombre: 'Óscar Lizcano', votos: 53839, pct: 0.23 },
    { nombre: 'Miguel Uribe Londoño', votos: 28657, pct: 0.12 },
    { nombre: 'Sondra Garvin', votos: 19889, pct: 0.09 },
    { nombre: 'Roy Barreras', votos: 14108, pct: 0.06 },
    { nombre: 'Luis Gilberto Murillo', votos: 13270, pct: 0.06 },
    { nombre: 'Carlos Caicedo', votos: 12694, pct: 0.05 },
    { nombre: 'Gustavo Matamoros', votos: 5627, pct: 0.02 },
  ],
};

@Injectable()
export class ActasService {
  constructor(private prisma: PrismaService) {}

  /** Reparte la siguiente acta pendiente SIN colisión (cola de trabajo). */
  async next(labeler: string) {
    // liberar bloqueos vencidos
    await this.prisma.$executeRawUnsafe(
      `UPDATE actas SET status='pending'
       WHERE status='in_progress' AND assigned_at < now() - interval '${LOCK_TTL_MIN} minutes'`,
    );
    // tomar una pendiente de forma atómica
    const rows = await this.prisma.$queryRawUnsafe<any[]>(
      `UPDATE actas SET status='in_progress', assigned_at=now(), labeler=$1
       WHERE acta_id = (
         SELECT acta_id FROM actas WHERE status='pending'
         ORDER BY random() LIMIT 1 FOR UPDATE SKIP LOCKED
       )
       RETURNING acta_id, dept, mun, zona, stand, mesa, hash`,
      labeler,
    );
    const r = rows[0];
    if (!r) return { done: true };

    const label = await this.prisma.label.findUnique({ where: { actaId: r.acta_id } });
    return {
      done: false,
      acta_id: r.acta_id,
      info: { dept: r.dept, mun: r.mun, zona: r.zona, stand: r.stand, mesa: r.mesa },
      prefill: label?.data ?? {},
    };
  }

  /** Devuelve el PDF: 1) caché, 2) disco local, 3) lo baja de la Registraduría y lo cachea. */
  async getPdf(actaId: string): Promise<Buffer | null> {
    const acta = await this.prisma.acta.findUnique({ where: { actaId } });
    if (!acta) return null;
    const cacheFile = join(CACHE_DIR, `${actaId}.pdf`);
    if (existsSync(cacheFile)) return readFileSync(cacheFile);
    const local = join(PDFS_DIR, acta.dept, `${actaId}.pdf`);
    if (existsSync(local)) return readFileSync(local);
    const zone = acta.zona.padStart(3, '0');
    const url = `${REG_BASE}/${acta.dept}/${acta.mun}/${zone}/${acta.stand}/${acta.mesa}/PRE/${acta.hash}?uuid=${crypto.randomUUID()}`;
    const res = await axios.get(url, {
      responseType: 'arraybuffer',
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 30000,
    });
    const buf = Buffer.from(res.data);
    try { mkdirSync(CACHE_DIR, { recursive: true }); writeFileSync(cacheFile, buf); } catch {}
    return buf;
  }

  async submit(actaId: string, labeler: string, votes: any) {
    await this.prisma.label.upsert({
      where: { actaId },
      create: { actaId, data: votes, labeler },
      update: { data: votes, labeler, createdAt: new Date() },
    });
    await this.prisma.acta.update({ where: { actaId }, data: { status: 'done' } });
    return { ok: true };
  }

  async flag(actaId: string, labeler: string, votes: any, nota: string) {
    await this.prisma.label.upsert({
      where: { actaId },
      create: { actaId, data: { votes, nota }, labeler },
      update: { data: { votes, nota }, labeler, createdAt: new Date() },
    });
    await this.prisma.acta.update({
      where: { actaId },
      data: { status: 'done', flagged: true },
    });
    return { ok: true };
  }

  async skip(actaId: string) {
    await this.prisma.acta.update({ where: { actaId }, data: { status: 'skipped' } });
    return { ok: true };
  }

  async stats() {
    const grouped = await this.prisma.acta.groupBy({
      by: ['status'],
      _count: true,
    });
    const map: Record<string, number> = {};
    grouped.forEach((g) => (map[g.status] = g._count));
    const total = await this.prisma.acta.count();
    const flagged = await this.prisma.acta.count({ where: { flagged: true } });
    const ranking = await this.prisma.label.groupBy({
      by: ['labeler'],
      _count: true,
      orderBy: { _count: { labeler: 'desc' } },
      take: 10,
    });
    return {
      total,
      done: map['done'] || 0,
      pending: map['pending'] || 0,
      in_progress: map['in_progress'] || 0,
      skipped: map['skipped'] || 0,
      flagged,
      ranking: ranking.map((r) => ({ labeler: r.labeler, n: r._count })),
    };
  }

  async flagged() {
    return this.prisma.acta.findMany({
      where: { flagged: true },
      include: { label: true },
      orderBy: { actaId: 'asc' },
      take: 500,
    });
  }

  async leaderboard() {
    const r = await this.prisma.label.groupBy({
      by: ['labeler'], _count: true,
      orderBy: { _count: { labeler: 'desc' } }, take: 50,
    });
    return r.map((x, i) => ({ rank: i + 1, labeler: x.labeler || 'anónimo', n: x._count }));
  }

  /** Resultados oficiales + avance de la verificación ciudadana (para Estadísticas). */
  async elecciones() {
    const total = await this.prisma.acta.count();
    const verificadas = await this.prisma.acta.count({ where: { status: 'done' } });
    const fraude = await this.prisma.acta.count({ where: { flagged: true } });
    return { oficial: OFICIAL, verificacion: { total, verificadas, fraude } };
  }
}
