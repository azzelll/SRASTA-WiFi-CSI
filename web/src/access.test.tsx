import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

vi.mock('@supabase/supabase-js',()=>({createClient:()=>({})}));
afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();});

describe('initial page without a saved login',()=>{
 it.each(['public','cloud'])('renders the correct entry page for %s access',async mode=>{
  vi.resetModules();
  vi.stubEnv('VITE_ACCESS_MODE',mode);
  vi.stubEnv('VITE_SUPABASE_URL','https://test.supabase.co');
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY','sb_publishable_test');
  vi.stubGlobal('window',{location:{search:''}});
  const {App}=await import('./app');
  const html=renderToStaticMarkup(<App />);
  if(mode==='public') {
   expect(html).toContain('Beranda');
   expect(html).toContain('Riwayat Aktivitas');
   expect(html).not.toContain('type="email"');
   expect(html).not.toContain('Kirim tautan masuk');
  } else {
   expect(html).not.toContain('Riwayat Aktivitas');
   expect(html).toContain('Memeriksa sesi');
  }
 });
});
