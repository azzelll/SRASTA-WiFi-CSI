import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Camera,
  ArrowRight,
  Bell,
  CheckCheck,
  ChevronRight,
  History,
  LogOut,
  Radio,
  ShieldCheck,
  Signal,
  TriangleAlert,
  Wifi,
  WifiOff,
} from "lucide-react";
import type {
  CareEvent,
  CommandReceipt,
  Device,
  Snapshot,
  SystemState,
} from "./types";
import {
  accessMode,
  cloud,
  cloudConfigured,
  commands,
  enablePush,
  listDevices,
  localSnapshot,
  remoteSnapshot,
  sendCommand,
} from "./connection";
import {
  eventSource,
  eventState,
  formatTime,
  isAlert,
  isFresh,
  receiverStatus,
  states,
} from "./status";

import { DashboardHome, DesignIcon, ConnectionIndicator, figmaAsset } from "./dashboard";
import { EventCard } from "./event-detail";
import { mergeReceipts } from "./receipts";
import { coalesceRefresh } from "./refresh";
export { StatusCard, MotionChart } from "./dashboard";

type Page = "home" | "alerts" | "history" | "event" | "devices" | "settings" | "about";
import { authorizedNotificationDevice, notificationRoute } from "./notification-route";
const pages = [
  { id: "home" as const, label: "Beranda", asset: "facdb.svg" },
  { id: "history" as const, label: "Riwayat Aktivitas", asset: "e537b.svg" },
  { id: "alerts" as const, label: "Riwayat Peringatan", asset: "28bc3.svg" },
  { id: "devices" as const, label: "Perangkat", asset: "b06e7.svg" },
  { id: "settings" as const, label: "Pengaturan", asset: "c4e30.svg" },
  { id: "about" as const, label: "Tentang Sistem", asset: "b0b96.svg" },
];

export function App() {
  const notificationTarget = useRef(notificationRoute(window.location.search));
  const [page, setPage] = useState<Page>("home");
  const [selectedEventUid, setSelectedEventUid] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [connectionError, setConnectionError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginMethod, setLoginMethod] = useState<"email" | "password">("email");
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(accessMode !== "cloud");
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [receipts, setReceipts] = useState<CommandReceipt[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [profile, setProfile] = useState({
    name: "Orang yang dipantau",
    room: "Ruang pemantauan",
  });
  const [emergency, setEmergency] = useState("");
  const [historyFilter, setHistoryFilter] = useState("all");
  const [motion, setMotion] = useState<{ time: number; value: number }[]>([]);
  const lastObserved = useRef<number | null>(null);
  const lastNotified = useRef(new Set<string>());
  const pendingIds = useRef(new Map<string, string>());
  const currentUserId = useRef<string | null>(null);
  const actionScope = useRef("");
  actionScope.current = `${userEmail || "local"}:${deviceId}`;
  const active = isFresh(snapshot, receivedAt, now);
  const events = snapshot?.events || [];
  const alerts = events.filter(isAlert).sort((a, b) =>
    Number(b.event_uid === notificationTarget.current.event) - Number(a.event_uid === notificationTarget.current.event) ||
    Number(!b.acknowledged_at_s) - Number(!a.acknowledged_at_s) || b.timestamp_s - a.timestamp_s,
  );
  const openAlerts = alerts.filter((event) => !event.acknowledged_at_s && !receipts.some(row => row.event_uid === event.event_uid && row.action === "acknowledge" && row.status === "applied"));
  const quickAckPending = !!openAlerts[0] && receipts.some(row => row.event_uid === openAlerts[0].event_uid && row.action === "acknowledge" && row.status === "pending");
  const state = snapshot?.state || "standby";
  const profileKey = `srasta:${currentUserId.current || "local"}:${deviceId || "local"}`;

  useEffect(() => {
    setProfile({
      name:
        localStorage.getItem(profileKey + ":alias") || "Orang yang dipantau",
      room: localStorage.getItem(profileKey + ":room") || "Ruang pemantauan",
    });
    setEmergency(localStorage.getItem(profileKey + ":emergency") || "");
  }, [profileKey]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (accessMode !== "cloud") return;
    if (!cloud) {
      setAuthReady(true);
      return;
    }
    cloud.auth.getSession().then(({ data }) => {
      currentUserId.current = data.session?.user.id || null;
      setUserEmail(data.session?.user.email || null);
      setAuthReady(true);
    });
    const { data } = cloud.auth.onAuthStateChange((_event, session) => {
      const nextId = session?.user.id || null;
      setUserEmail(session?.user.email || null);
      if (nextId === currentUserId.current) return;
      currentUserId.current = nextId;
      setSnapshot(null);
      setDeviceId("");
      setDevices([]);
      setReceipts([]);
      setMotion([]);
      lastNotified.current.clear();
      pendingIds.current.clear();
    });
    return () => data.subscription.unsubscribe();
  }, []);
  useEffect(() => {
    if (!userEmail || !cloud) return;
    let cancelled = false;
    listDevices()
      .then((rows) => {
        if (!cancelled) {
          setDevices(rows);
          const requested = notificationTarget.current.device;
          const target = authorizedNotificationDevice(rows, requested);
          setDeviceId(target || rows[0]?.id || "");
          if (requested && !target) {
            notificationTarget.current = {device: "", event: ""};
            setNotice("Perangkat pada notifikasi tidak tersedia untuk akun ini.");
          } else if (target && notificationTarget.current.event) {
            setPage("alerts");
          }
        }
      })
      .catch((error) => setConnectionError(error.message));
    return () => {
      cancelled = true;
    };
  }, [userEmail]);
  useEffect(() => {
    let cancelled = false;
    setSnapshot(null);
    setMotion([]);
    setReceipts([]);
    setSelectedEventUid(null);
    setBusy(false);
    pendingIds.current.clear();
    lastObserved.current = null;
    async function readSnapshot() {
      try {
        const next =
          accessMode === "cloud"
            ? deviceId
              ? await remoteSnapshot(deviceId)
              : null
            : await localSnapshot();
        if (cancelled) return;
        setSnapshot(previous => previous && next && previous.updated_at_s > next.updated_at_s ? previous : next);
        setReceivedAt(Date.now());
        setConnectionError("");
        if (accessMode === "cloud" && deviceId) {
          const nextReceipts = await commands(deviceId);
          if (!cancelled) setReceipts(rows => mergeReceipts(rows, nextReceipts));
        }
      } catch (error) {
        if (!cancelled)
          setConnectionError(
            error instanceof Error ? error.message : "Koneksi terganggu.",
          );
      }
    }
    if (accessMode === "cloud" && (!userEmail || !deviceId)) return;
    const poller = coalesceRefresh(readSnapshot);
    const refresh = () => { void poller.request(); };
    refresh();
    const interval = setInterval(refresh, accessMode === "cloud" ? 5000 : 3000);
    const source =
      accessMode === "local" ? new EventSource("/api/caregiver/stream") : null;
    source?.addEventListener("snapshot", (event) => {
      if (!cancelled) {
        try {
          const next = JSON.parse((event as MessageEvent).data) as Snapshot;
          setSnapshot(previous => previous && previous.updated_at_s > next.updated_at_s ? previous : next);
          setReceivedAt(Date.now());
          setConnectionError("");
        } catch {
          setConnectionError("Pembaruan perangkat belum dapat dibaca. Mencoba kembali.");
        }
      }
    });
    const channel =
      cloud && deviceId
        ? cloud
            .channel(`device-status:${deviceId}`)
            .on(
              "postgres_changes",
              {
                event: "*",
                schema: "public",
                table: "device_status",
                filter: `device_id=eq.${deviceId}`,
              },
              refresh,
            )
            .subscribe()
        : null;
    return () => {
      cancelled = true;
      poller.close();
      clearInterval(interval);
      source?.close();
      if (channel && cloud) cloud.removeChannel(channel);
    };
  }, [userEmail, deviceId]);
  useEffect(() => {
    if (
      snapshot?.observed_at_s &&
      snapshot.observed_at_s !== lastObserved.current &&
      snapshot.source === "live" &&
      snapshot.motion_energy !== null
    ) {
      lastObserved.current = snapshot.observed_at_s;
      setMotion((rows) =>
        [
          ...rows,
          { time: snapshot.observed_at_s!, value: snapshot.motion_energy! },
        ].filter(row => row.time >= snapshot.observed_at_s! - 3600).slice(-7200),
      );
    }
    for (const event of snapshot?.events || []) {
      if (!isAlert(event) || lastNotified.current.has(event.event_uid))
        continue;
      lastNotified.current.add(event.event_uid);
      if (
        Date.now() / 1000 - event.timestamp_s > 20 ||
        document.visibilityState !== "visible" ||
        !("Notification" in window) ||
        Notification.permission !== "granted"
      )
        continue;
      const title = "SRASTA · " + states[eventState(event.state)].label;
      const options = {
        body:
          eventSource(event) === "Simulasi"
            ? "Peringatan simulasi untuk pengujian."
            : "Buka Peringatan untuk memeriksa kondisi.",
        tag: event.event_uid,
        data: {event_uid: event.event_uid, device_id: deviceId},
      };
      // Mobile browsers require service-worker notifications; constructor errors
      // must never interrupt dashboard updates.
      if ("serviceWorker" in navigator)
        navigator.serviceWorker
          .getRegistration()
          .then((registration) => {
            if (registration)
              return registration.showNotification(title, options);
            new Notification(title, options);
          })
          .catch(() => {});
      else {
        try {
          new Notification(title, options);
        } catch {
          /* Dashboard remains active. */
        }
      }
    }
  }, [snapshot]);

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      const { error } =
        loginMethod === "email"
          ? await cloud!.auth.signInWithOtp({
              email,
              options: {
                emailRedirectTo: window.location.origin,
                shouldCreateUser: false,
              },
            })
          : await cloud!.auth.signInWithPassword({ email, password });
      if (error)
        setNotice("Belum bisa masuk. Periksa akun caregiver dan coba lagi.");
      else if (loginMethod === "email")
        setNotice(
          "Tautan masuk dikirim. Buka email di perangkat ini untuk melanjutkan.",
        );
    } catch {
      setNotice(
        "Layanan masuk belum merespons. Coba lagi setelah koneksi pulih.",
      );
    } finally {
      setPassword("");
      setBusy(false);
    }
  }
  async function act(event: CareEvent, action: "acknowledge" | "assistance") {
    if (receipts.some(row => row.event_uid === event.event_uid && row.action === action && ["pending", "applied"].includes(row.status))) return;
    const scope = actionScope.current;
    setBusy(true);
    setNotice("");
    const key = `${event.event_uid}:${action}`;
    const pendingId = pendingIds.current.get(key);
    const prior = receipts.find((receipt) => receipt.id === pendingId);
    const id =
      pendingId && !["expired", "rejected"].includes(prior?.status || "")
        ? pendingId
        : crypto.randomUUID();
    pendingIds.current.set(key, id);
    try {
      const receipt = await sendCommand(deviceId, event.event_uid, action, id);
      if (scope !== actionScope.current) return;
      setReceipts(rows => mergeReceipts(rows, [receipt]));
      setNotice(
        receipt.status === "applied"
          ? "Tindakan tersimpan di edge."
          : receipt.status === "pending"
            ? "Menunggu konfirmasi edge."
            : receipt.status === "expired"
              ? "Perintah kedaluwarsa. Kirim ulang jika masih diperlukan."
              : "Kejadian tidak dapat ditindaklanjuti.",
      );
      if (receipt.status === "applied" || receipt.status === "expired")
        pendingIds.current.delete(key);
      if (accessMode === "local") {
        const next = await localSnapshot();
        if (scope !== actionScope.current) return;
        setSnapshot(next);
        setReceivedAt(Date.now());
      }
    } catch (error) {
      if (scope !== actionScope.current) return;
      setNotice(
        error instanceof Error ? error.message : "Perintah belum berhasil.",
      );
    } finally {
      if (scope === actionScope.current) setBusy(false);
    }
  }
  async function simulate(next: SystemState) {
    setBusy(true);
    try {
      const response = await fetch(`/demo/state/${next}`, { method: "POST" });
      if (!response.ok) throw new Error();
      setSnapshot(await localSnapshot());
      setReceivedAt(Date.now());
      setNotice("Status simulasi: " + states[next].label);
    } catch {
      setNotice("Pengendali simulasi tidak tersedia.");
    } finally {
      setBusy(false);
    }
  }
  function saveProfile() {
    localStorage.setItem(profileKey + ":alias", profile.name);
    localStorage.setItem(profileKey + ":room", profile.room);
    localStorage.setItem(profileKey + ":emergency", emergency);
    setNotice("Label dan kontak tersimpan untuk perangkat ini di browser.");
  }

  if (accessMode === "cloud" && !userEmail)
    return (
      <main className="login">
        <header className="login-brand">
          <Logo />
          <span>Pemantauan rumah</span>
        </header>
        <section className="login-card">
          <span className="login-step">AKUN CAREGIVER</span>
          <h1>Masuk</h1>
          <p>Masukkan email akun Anda untuk membuka pemantauan.</p>
          {!cloudConfigured ? (
            <div className="inline-warning">
              Layanan cloud belum dikonfigurasi. URL proyek dan publishable key
              diperlukan.
            </div>
          ) : !authReady ? (
            <p>Memeriksa sesi…</p>
          ) : (
            <form onSubmit={login}>
              <label>
                Email
                <input
                  type="email"
                  autoComplete="username"
                  placeholder="nama@email.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              {loginMethod === "password" && (
                <label>
                  Kata sandi
                  <input
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
              )}
              <button className="primary" disabled={busy}>
                {loginMethod === "email" ? "Kirim tautan masuk" : "Masuk"}{" "}
                <ArrowRight size={18} />
              </button>
              <button
                type="button"
                className="text-button login-method"
                disabled={busy}
                onClick={() => {
                  setLoginMethod(
                    loginMethod === "email" ? "password" : "email",
                  );
                  setPassword("");
                  setNotice("");
                }}
              >
                {loginMethod === "email"
                  ? "Masuk dengan kata sandi"
                  : "Masuk melalui email"}
              </button>
            </form>
          )}
          {notice && <p role="alert">{notice}</p>}
          <small>Gunakan email yang telah didaftarkan pemilik perangkat.</small>
        </section>
        <footer className="login-footer"><ShieldCheck size={15} /> Data pemantauan hanya tersedia untuk caregiver terdaftar.</footer>
      </main>
    );

  return (
    <div className="app-shell">
      <aside className={"sidebar " + (state === "standby" ? "standby-sidebar" : "")}>
        <Logo />
        <nav aria-label="Navigasi utama">
          {pages.map(item => <button key={item.id} className={page === item.id ? "selected" : ""} aria-current={page === item.id ? "page" : undefined} onClick={() => setPage(item.id)}>
            <DesignIcon file={item.asset} />
            <span>{item.label}</span>
            {item.id === "alerts" && openAlerts.length > 0 && <b>{openAlerts.length}</b>}
          </button>)}
        </nav>
        <img className="sidebar-illustration" src={figmaAsset("8ebb4.png")} alt="" />
        <div className={"quick-caregiver " + (state === "critical" ? "critical" : "")}>
          {emergency ? <a className="quick-help" href={"tel:" + emergency.replace(/[^+\d]/g, "")}><DesignIcon file="5d7ba.svg" />Bantuan Cepat</a> : <button className="quick-help" onClick={() => { setPage("settings"); setNotice("Isi kontak darurat agar bantuan cepat dapat dihubungi."); }}><DesignIcon file="5d7ba.svg" />Bantuan Cepat</button>}
          {state === "critical" && openAlerts[0] && <button className="quick-ack" disabled={busy || quickAckPending} onClick={() => act(openAlerts[0], "acknowledge")}>{quickAckPending ? "Menunggu perangkat" : "Saya sudah melihat"}</button>}
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <h1>{page === "home" ? "Dashboard IoT Berbasis Web untuk Caregiver" : page === "event" ? "Detail kejadian" : pages.find(item => item.id === page)?.label}</h1>
          <div className="topbar-right">
            <ConnectionIndicator snapshot={snapshot} active={active} />
            <div className="dashboard-clock"><DesignIcon file="a554b.svg" /><div><time>{new Date(now).toLocaleTimeString("en-GB")}</time><span>{new Date(now).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })}</span></div></div>
          </div>
        </header>
        <main className={page === "home" ? "dashboard-main" : "secondary-main"}>
          {connectionError && (
            <div className="inline-warning" role="alert">
              <WifiOff size={18} />
              {connectionError}
            </div>
          )}
          {snapshot?.simulation && (
            <div className="simulation-banner">
              <Radio size={18} />
              <strong>
                {snapshot.source === "replay"
                  ? "REPLAY REKAMAN"
                  : "MODE SIMULASI"}
              </strong>
              <span>
                Hasil ini untuk pengujian. Status tidak membuktikan kejadian
                dari CSI langsung.
              </span>
            </div>
          )}
          {!active && !snapshot?.simulation && (
            <div className="offline-banner">
              <WifiOff size={18} />
              <div>
                <strong>Pemantauan belum aktif</strong>
                <p>
                  {snapshot
                    ? "Data terakhir ditampilkan. Kondisi terkini belum dapat dipastikan."
                    : "Menunggu koneksi edge dan data CSI yang valid."}
                </p>
              </div>
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {notice}
              <button aria-label="Tutup pesan" onClick={() => setNotice("")}>
                ×
              </button>
            </div>
          )}
          {accessMode === "cloud" && devices.length === 0 && (
            <div className="empty">
              <ShieldCheck />
              <h2>Belum ada perangkat terhubung</h2>
              <p>
                Minta pemilik sistem mendaftarkan akun Anda sebagai caregiver.
              </p>
            </div>
          )}
          {page === "home" && <DashboardHome snapshot={snapshot} active={active} name={profile.name} room={profile.room} now={now} motion={motion} onAlerts={() => setPage("alerts")} onHistory={() => setPage("history")} />}
          {page === "alerts" && (
            <>
              <div className="intro">
                <div>
                  <h2>Peringatan & tindak lanjut</h2>
                  <p>{openAlerts.length} peringatan belum diakui.</p>
                </div>
              </div>
              {alerts.length ? (
                alerts.map(event => (
                  <EventCard key={event.event_uid} event={event} snapshot={snapshot} receipts={receipts} busy={busy} room={profile.room} emergency={emergency}
                    target={event.event_uid === notificationTarget.current.event} onAction={act}
                    onSetupEmergency={() => { setPage("settings"); setNotice("Isi nomor kontak darurat agar tombol panggilan dapat digunakan."); }} />
                ))
              ) : (
                <section className="card">
                  <EmptyEvents />
                </section>
              )}
            </>
          )}
          {page === "event" && <>
            <button className="text-button event-back" onClick={() => setPage("history")}>← Kembali ke riwayat</button>
            {events.find(event => event.event_uid === selectedEventUid) ?
              <EventCard event={events.find(event => event.event_uid === selectedEventUid)!} snapshot={snapshot} receipts={receipts} busy={busy} room={profile.room} emergency={emergency} onAction={act}
                onSetupEmergency={() => { setPage("settings"); setNotice("Isi kontak darurat terlebih dahulu."); }} /> :
              <section className="card"><p>Kejadian ini belum tersedia dalam riwayat yang diterima. Muat ulang riwayat atau periksa koneksi perangkat.</p></section>}
          </>}
          {page === "history" && (
            <>
              <div className="intro">
                <div>
                  <h2>Riwayat pemantauan</h2>
                  <p>
                    Kejadian yang tercatat di edge, beserta sumber dan respons
                    caregiver.
                  </p>
                </div>
              </div>
              <div className="filter-row">
                {[
                  ["all", "Semua"],
                  ["alerts", "Peringatan"],
                  ["ack", "Sudah diakui"],
                ].map(([value, label]) => (
                  <button
                    className={historyFilter === value ? "active" : ""}
                    aria-pressed={historyFilter === value}
                    key={value}
                    onClick={() => setHistoryFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <section className="card history-list">
                {events
                  .filter(
                    (event) =>
                      historyFilter === "all" ||
                      (historyFilter === "alerts" && isAlert(event)) ||
                      (historyFilter === "ack" && !!event.acknowledged_at_s),
                  )
                  .map((event) => (
                    <EventRow
                      key={event.event_uid}
                      event={event}
                      onOpen={() => { setSelectedEventUid(event.event_uid); setPage("event"); }}
                    />
                  ))}
                {events.filter(
                  (event) =>
                    historyFilter === "all" ||
                    (historyFilter === "alerts" && isAlert(event)) ||
                    (historyFilter === "ack" && !!event.acknowledged_at_s),
                ).length === 0 && (
                  <div className="empty-events">
                    <History size={28} />
                    <div>
                      <strong>Belum ada kejadian pada tampilan ini</strong>
                      <p>Riwayat akan muncul setelah diterima dari edge.</p>
                    </div>
                  </div>
                )}
              </section>
            </>
          )}
          {(page === "settings" || page === "devices") && (
            <>
              <div className="intro">
                <div>
                  <h2>{page === "devices" ? "Perangkat pemantauan" : "Pengaturan & akun"}</h2>
                  <p>Atur pemantauan dan cara menerima peringatan.</p>
                </div>
              </div>
              <div className="settings-grid">
                {page === "settings" && <section className="card">
                  <h3>Area pemantauan</h3>
                  {accessMode === "cloud" && (
                    <label>
                      Perangkat
                      <select
                        value={deviceId}
                        onChange={(e) => setDeviceId(e.target.value)}
                      >
                        {devices.map((device) => (
                          <option key={device.id} value={device.id}>
                            {device.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label>
                    Label orang
                    <input
                      value={profile.name}
                      maxLength={60}
                      onChange={(e) =>
                        setProfile({ ...profile, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Ruangan
                    <input
                      value={profile.room}
                      maxLength={60}
                      onChange={(e) =>
                        setProfile({ ...profile, room: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Kontak darurat
                    <input
                      type="tel"
                      value={emergency}
                      maxLength={24}
                      placeholder="Nomor yang akan Anda hubungi"
                      onChange={(e) => setEmergency(e.target.value)}
                    />
                  </label>
                  <button className="primary" onClick={saveProfile}>
                    Simpan
                  </button>
                  <small>
                    Label dan nomor hanya disimpan pada browser ini.
                  </small>
                </section>}
                {page === "devices" && <section className="card">
                  <h3>Status perangkat</h3>
                  {accessMode === "cloud" && <label>Perangkat<select value={deviceId} onChange={e => setDeviceId(e.target.value)}>{devices.map(device => <option key={device.id} value={device.id}>{device.label}</option>)}</select></label>}
                  <HealthRow icon={Wifi} label="Edge processor" ok={active && snapshot?.source === "live"} value={active ? snapshot?.source === "simulator" ? "Simulasi" : "Online" : "Offline"} />
                  <HealthRow icon={Radio} label="Receiver CSI" {...receiverStatus(snapshot, active)} />
                  <HealthRow icon={Camera} label="Validasi kamera" ok={active && !!snapshot?.camera.available} value={!active ? "Status belum terkini" : snapshot?.camera.active ? "Sedang memvalidasi" : snapshot?.camera.available ? "Siap saat anomali" : "Belum tersedia"} />
                  <HealthRow icon={Bell} label="Alarm lokal" ok={active && !!snapshot?.alarm.available} value={!active ? "Status belum terkini" : snapshot?.alarm.active ? "Berbunyi" : snapshot?.alarm.available ? "Siap" : "Belum tersedia"} />
                  <HealthRow icon={Signal} label="Blynk" ok={active && !!snapshot?.blynk_connected} value={!active ? "Status belum terkini" : snapshot?.blynk_connected ? "Terhubung" : "Tidak terhubung"} />
                  <HealthRow icon={Wifi} label="Cloud" ok={active && !!snapshot?.remote.connected} value={!active ? "Status belum terkini" : snapshot?.remote.connected ? "Terhubung" : "Tidak terhubung"} />
                  <dl className="metrics spaced"><dt>Keberadaan</dt><dd>{active ? ({present:"Terdeteksi",empty:"Ruangan kosong",unknown:"Belum pasti"}[snapshot?.presence || "unknown"]) : "Belum pasti"}</dd><dt>Pola pernapasan</dt><dd>{active && snapshot?.breathing_condition ? ({sleep:"Tidur",normal:"Normal",empty:"Ruangan kosong"}[snapshot.breathing_condition]) : "Belum tersedia"}</dd></dl>
                </section>}
                {page === "devices" && <section className="card">
                  <h3>Koneksi & kualitas data</h3>
                  {!active && <p>Catatan terakhir dari edge; nilai di bawah bukan pengukuran terkini.</p>}
                  <dl className="metrics">
                    <dt>Mode akses</dt>
                    <dd>{accessMode === "cloud" ? "Jarak jauh" : "Lokal"}</dd>
                    <dt>Sumber data</dt>
                    <dd>{snapshot?.source || "Belum tersedia"}</dd>
                    <dt>Paket valid</dt>
                    <dd>
                      {snapshot?.accepted_frames.toLocaleString("id-ID") || 0}
                    </dd>
                    <dt>Laju penerimaan</dt>
                    <dd>{snapshot?.capture_rate_hz ?? 0} Hz</dd>
                    <dt>Kehilangan paket</dt>
                    <dd>
                      {snapshot?.packet_loss_rate != null
                        ? (snapshot.packet_loss_rate * 100).toFixed(1) + "%"
                        : "Belum diukur"}
                    </dd>
                    <dt>Paket dikarantina</dt>
                    <dd>{snapshot?.quarantined_frames || 0}</dd>
                    <dt>Inferensi</dt>
                    <dd>
                      {snapshot?.inference_ms != null
                        ? snapshot.inference_ms.toFixed(1) + " ms"
                        : "Belum tersedia"}
                    </dd>
                    <dt>Reconnect RX</dt>
                    <dd>{snapshot?.serial_reconnects || 0}</dd>
                    <dt>Data CSI terakhir</dt>
                    <dd>{formatTime(snapshot?.observed_at_s || null)}</dd>
                  </dl>
                  <div className="model-note">
                    <strong>{snapshot?.model.label || "Model edge"}</strong>
                    <p>{snapshot?.model.validation || "Menunggu edge."}</p>
                    <small>
                      Deteksi keberadaan dan kelas aktivitas lengkap masih
                      memerlukan model yang tervalidasi. Estimasi napas dan
                      kamera memiliki gerbang kualitas sendiri.
                    </small>
                  </div>
                </section>}
                {page === "settings" && <section className="card">
                  <h3>Notifikasi</h3>
                  <p>Terima peringatan untuk perangkat yang Anda pantau.</p>
                  <button
                    className="secondary"
                    onClick={() =>
                      enablePush(deviceId)
                        .then(setNotice)
                        .catch(() => setNotice("Push belum dapat diaktifkan."))
                    }
                  >
                    <Bell size={18} /> Aktifkan notifikasi
                  </button>
                  <small>
                    Push jarak jauh memerlukan HTTPS, konfigurasi cloud, dan
                    izin browser. Di iPhone, buka dari Home Screen.
                  </small>
                  <h3 className="spaced">Pasang ke Home Screen</h3>
                  <p>
                    Di Safari: Bagikan → Tambahkan ke Layar Utama. Di Chrome:
                    menu → Instal aplikasi.
                  </p>
                </section>}
                {page === "settings" && <section className="card">
                  <h3>Akun caregiver</h3>
                  <p>{userEmail || "Sesi lokal pada perangkat edge"}</p>
                  {cloud && (
                    <button
                      className="secondary"
                      onClick={() => cloud?.auth.signOut()}
                    >
                      <LogOut size={18} /> Keluar
                    </button>
                  )}
                  <p className="privacy">
                    <ShieldCheck size={18} /> CSI mentah dan video tetap di
                    edge. App menerima ringkasan kondisi dan kejadian.
                  </p>
                </section>}
              </div>
            </>
          )}
          {page === "about" && <section className="card about-system"><h2>Tentang SRASTA</h2><p>Sistem Monitoring Keselamatan Lansia Berbasis WiFi CSI dan Edge AI.</p><h3>Pemantauan di rumah</h3><p>CSI digunakan untuk membaca keberadaan, gerakan, durasi diam, indikasi jatuh, dan pola pernapasan. Raspberry Pi memproses data secara lokal.</p><h3>Validasi saat diperlukan</h3><p>Kamera hanya digunakan untuk memeriksa postur saat anomali. App menerima ringkasan dan koordinat skeleton yang terikat ke kejadian. Gambar kamera dan CSI mentah tetap di edge. Skeleton adalah cuplikan saat kejadian, bukan video langsung; postur berbaring belum memastikan tidur atau jatuh.</p><h3>Membaca kondisi</h3><p>Siaga, normal, inaktif, anomali, dan kritis ditampilkan sesuai data edge. Saat data berhenti, kondisi terakhir tetap terlihat dan pemantauan ditandai offline.</p><h3>Periksa hasil sebelum bertindak</h3><p>Model masih memerlukan validasi lingkungan. Estimasi napas merupakan indikasi pola, bukan diagnosis.</p></section>}
          {snapshot?.source === "simulator" && accessMode === "local" && (
            <details className="demo-controls">
              <summary>Pengendali pengujian · simulasi</summary>
              <p>
                Ubah status untuk memeriksa tampilan, alarm, dan respons
                caregiver.
              </p>
              <div>
                {(Object.keys(states) as SystemState[]).map((next) => (
                  <button
                    key={next}
                    disabled={busy}
                    onClick={() => simulate(next)}
                  >
                    {states[next].label}
                  </button>
                ))}
              </div>
            </details>
          )}
        </main>
        <footer className="dashboard-footer">SRASTA - Sistem Monitoring Keselamatan Lansia Berbasis WiFi CSI dan Edge AI</footer>
      </div>
      <nav className="bottom-nav" aria-label="Navigasi mobile">
        {pages.map((item) => (
          <button
            key={item.id}
            className={page === item.id ? "selected" : ""}
            onClick={() => setPage(item.id)}
          >
            <DesignIcon file={item.asset} />
            <span>{item.label}</span>
            {item.id === "alerts" && openAlerts.length > 0 && (
              <b>{openAlerts.length}</b>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
}

function Logo() {
  return <div className="logo"><img src={figmaAsset("55645.svg")} alt="" /><div><strong>SRASTA</strong><small>Monitoring Keselamatan<br />Lansia Berbasis WiFi CSI<br />dan Edge AI</small></div></div>;
}
function HealthRow({
  icon: Icon,
  label,
  ok,
  value,
}: {
  icon: typeof Wifi;
  label: string;
  ok: boolean;
  value: string;
}) {
  return (
    <div className="health-row">
      <Icon size={18} />
      <span>{label}</span>
      <strong className={ok ? "ok" : "muted"}>
        <i />
        {value}
      </strong>
    </div>
  );
}
function EventRow({ event, onOpen }: { event: CareEvent; onOpen: () => void }) {
  const state = eventState(event.state);
  return (
    <button className="event-row" onClick={onOpen}>
      <span className={`event-icon ${state}`}>
        {isAlert(event) ? <TriangleAlert size={20} /> : <Activity size={20} />}
      </span>
      <div>
        <strong>{states[state].label}</strong>
        <span>
          {formatTime(event.timestamp_s)} · {eventSource(event)}
        </span>
      </div>
      <span className="event-ack">
        {event.acknowledged_at_s ? (
          <CheckCheck size={18} />
        ) : isAlert(event) ? (
          "Perlu respons"
        ) : (
          ""
        )}
      </span>
      <ChevronRight size={18} />
    </button>
  );
}
function EmptyEvents() {
  return (
    <div className="empty-events">
      <ShieldCheck size={28} />
      <div>
        <strong>Belum ada peringatan tercatat</strong>
        <p>Kejadian akan tampil setelah diterima dari edge.</p>
      </div>
    </div>
  );
}
