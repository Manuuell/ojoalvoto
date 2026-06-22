/**
 * Carga el manifest.csv de actas en la base de datos.
 * Uso:  DATABASE_URL=... MANIFEST=/data/manifest.csv ts-node src/seed.ts
 */
import { PrismaClient } from '@prisma/client';
import { parse } from 'csv-parse/sync';
import { readFileSync } from 'fs';

const prisma = new PrismaClient();
const MANIFEST = process.env.MANIFEST || '/data/manifest.csv';

async function main() {
  const before = await prisma.acta.count();
  console.log(`Actas ya en BD: ${before} (se conservan con su estado; solo se AGREGAN las nuevas)`);
  const csv = readFileSync(MANIFEST, 'utf-8');
  const rows: any[] = parse(csv, { columns: true, skip_empty_lines: true });
  const data = rows
    .filter((r) => ['true', '1', ''].includes(String(r.ok ?? 'True').toLowerCase()))
    .map((r) => ({
      actaId: r.acta_id,
      dept: r.dept,
      mun: r.mun,
      zona: r.zona,
      stand: r.stand,
      mesa: r.mesa,
      hash: r.hash || '',
    }));

  // Insertar en lotes
  const BATCH = 1000;
  for (let i = 0; i < data.length; i += BATCH) {
    await prisma.acta.createMany({
      data: data.slice(i, i + BATCH),
      skipDuplicates: true,
    });
    console.log(`  procesadas ${Math.min(i + BATCH, data.length)}/${data.length}`);
  }
  const after = await prisma.acta.count();
  console.log(`Listo. Total actas en BD: ${after} (nuevas agregadas: ${after - before})`);
}

main().finally(() => prisma.$disconnect());
