import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MotionChart } from './app';

it('shows the measured Pi motion range instead of compressing it below a fixed floor',()=>{
 const output=renderToStaticMarkup(<MotionChart values={[0.00010,0.00020,0.00012]} />);
 const points=output.match(/<polyline points="([^"]+)"/);
 expect(points).not.toBeNull();
 const heights=points![1].split(' ').map(point=>Number(point.split(',')[1]));
 expect(Math.max(...heights)-Math.min(...heights)).toBeGreaterThan(35);
 expect(output).toContain('Skala otomatis');
 expect(output).toContain('2.0e-4');
});

it('keeps a zero signal flat without inventing movement',()=>{
 const output=renderToStaticMarkup(<MotionChart values={[0,0,0]} />);
 const points=output.match(/<polyline points="([^"]+)"/);
 expect(points![1].split(' ').map(point=>Number(point.split(',')[1]))).toEqual([110,110,110]);
 expect(output).not.toContain('NaN');
 expect(output).not.toContain('Infinity');
});
