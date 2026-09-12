// SRASTA ESP32-S3 LLTF/HT20 emitter, ESP-IDF 5.4.0.
// ESP-NOW setup follows Espressif's public-domain get-started examples.
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "srasta_config.h"
#ifndef SRASTA_HOTSPOT
#define SRASTA_HOTSPOT 0
#endif
#if SRASTA_HOTSPOT
#include "srasta_hotspot.local.h"
#include "ping/ping_sock.h"
#include "lwip/ip_addr.h"
#include "freertos/event_groups.h"
static EventGroupHandle_t connection_events;
static esp_netif_t *station;
static volatile unsigned disconnect_reason=0;
static volatile uint32_t ping_replies=0,ping_timeouts=0,ping_reply_ms=0;
static void ping_success(esp_ping_handle_t handle,void *arg) {
    (void)arg;
    uint32_t elapsed=0;
    esp_ping_get_profile(handle,ESP_PING_PROF_TIMEGAP,&elapsed,sizeof(elapsed));
    ping_reply_ms=elapsed; ping_replies++;
}
static void ping_timeout(esp_ping_handle_t handle,void *arg) {
    (void)handle; (void)arg; ping_timeouts++;
}
static void network_event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    if(base==WIFI_EVENT && id==WIFI_EVENT_STA_START) esp_wifi_connect();
    if(base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED) {
        disconnect_reason=((wifi_event_sta_disconnected_t *)data)->reason;
        xEventGroupClearBits(connection_events,1); esp_wifi_connect();
    }
    if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) xEventGroupSetBits(connection_events,1);
}
#endif

static const uint8_t tx_mac[6] = SRASTA_TX_MAC;
#if SRASTA_ROLE_TX
static const uint8_t broadcast[6] = {255,255,255,255,255,255};
#endif

static void radio_start(void) {
    esp_err_t nvs=nvs_flash_init();
    if(nvs==ESP_ERR_NVS_NO_FREE_PAGES || nvs==ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase()); nvs=nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
#if SRASTA_HOTSPOT
    connection_events=xEventGroupCreate();
    station=esp_netif_create_default_wifi_sta();
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,network_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL));
#endif
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA,WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G|WIFI_PROTOCOL_11N));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA,WIFI_BW_HT20));
#if SRASTA_ROLE_TX
    ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA,tx_mac));
#endif
#if SRASTA_HOTSPOT
    wifi_config_t wifi={0};
    memcpy(wifi.sta.ssid,SRASTA_WIFI_SSID,sizeof(SRASTA_WIFI_SSID)-1);
    memcpy(wifi.sta.password,SRASTA_WIFI_PASSWORD,sizeof(SRASTA_WIFI_PASSWORD)-1);
    wifi.sta.channel=SRASTA_CHANNEL;
    wifi.sta.bssid_set=true;
    memcpy(wifi.sta.bssid,tx_mac,6);
    wifi.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&wifi));
#endif
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
#if !SRASTA_HOTSPOT
    ESP_ERROR_CHECK(esp_wifi_set_channel(SRASTA_CHANNEL,WIFI_SECOND_CHAN_NONE));
#endif
    ESP_ERROR_CHECK(esp_now_init());
}

#if !SRASTA_ROLE_TX
typedef struct {
    uint64_t sequence;
    int64_t timestamp;
    int rssi,noise_floor,channel,mcs,rx_state;
    bool first_word_invalid;
    int8_t iq[128];
} frame_t;
static QueueHandle_t frames;
static uint64_t sequence=0;
static volatile uint32_t rejected=0,dropped=0;
static volatile unsigned last_len=0,last_mode=0;

static void receive_csi(void *ctx,wifi_csi_info_t *info) {
    (void)ctx;
    if (!info || !info->buf || memcmp(info->mac,tx_mac,6)!=0) return;
    uint64_t seq=sequence++;
    const wifi_pkt_rx_ctrl_t *rx=&info->rx_ctrl;
    last_len=info->len; last_mode=rx->sig_mode;
    if (info->len!=128 || rx->cwb!=0 || rx->sig_mode!=1 || rx->channel!=SRASTA_CHANNEL || rx->rx_state!=0 || rx->mcs>7) {
        rejected++; return;
    }
    frame_t frame={.sequence=seq,.timestamp=esp_timer_get_time(),.rssi=rx->rssi,.noise_floor=rx->noise_floor,.channel=rx->channel,.mcs=rx->mcs,.rx_state=rx->rx_state,.first_word_invalid=info->first_word_invalid};
    memcpy(frame.iq,info->buf,128);
    // Never block or print from the WiFi task; copy before the driver reuses buf.
    if (xQueueSend(frames,&frame,0)!=pdTRUE) dropped++;
}

static void emit_frame(const frame_t *f) {
    // Only the main consumer calls this function; keep the bounded buffer off
    // its small FreeRTOS stack (WiFi callbacks never touch this buffer).
    static char line[2048];
    int used=snprintf(line,sizeof(line),"{\"version\":1,\"sequence\":%"PRIu64",\"local_timestamp_us\":%"PRId64",\"sender_mac\":\"%02x:%02x:%02x:%02x:%02x:%02x\",\"rssi\":%d,\"noise_floor\":%d,\"channel\":%d,\"bandwidth\":\"HT20\",\"sig_mode\":\"HT\",\"mcs\":%d,\"rx_state\":%d,\"len\":128,\"first_word_invalid\":%s,\"iq_bytes\":[",f->sequence,f->timestamp,tx_mac[0],tx_mac[1],tx_mac[2],tx_mac[3],tx_mac[4],tx_mac[5],f->rssi,f->noise_floor,f->channel,f->mcs,f->rx_state,f->first_word_invalid?"true":"false");
    for(int i=0;i<128;i++) used+=snprintf(line+used,sizeof(line)-used,"%s%d",i?",":"",f->iq[i]);
    snprintf(line+used,sizeof(line)-used,"]}\n");
    fputs(line,stdout);
}
#endif

void app_main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    radio_start();
#if SRASTA_ROLE_TX
    esp_now_peer_info_t peer={.channel=SRASTA_CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};
    memcpy(peer.peer_addr,broadcast,6);
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    esp_now_rate_config_t rate={.phymode=WIFI_PHY_MODE_HT20,.rate=WIFI_PHY_RATE_MCS0_LGI,.ersu=false,.dcm=false};
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(peer.peer_addr,&rate));
    uint32_t counter=0,errors=0;
    TickType_t wake=xTaskGetTickCount();
    while(1) {
        if (esp_now_send(broadcast,(const uint8_t *)&counter,sizeof(counter))!=ESP_OK) errors++;
        if(counter%SRASTA_RATE_HZ==0) printf("# SRASTA role=TX revision=%s channel=%d target_hz=%d sent=%"PRIu32" errors=%"PRIu32"\n",SRASTA_REVISION,SRASTA_CHANNEL,SRASTA_RATE_HZ,counter,errors);
        counter++;
        vTaskDelayUntil(&wake,pdMS_TO_TICKS(1000/SRASTA_RATE_HZ));
    }
#else
    frames=xQueueCreate(64,sizeof(frame_t));
    configASSERT(frames);
    wifi_csi_config_t csi={.lltf_en=true,.htltf_en=false,.stbc_htltf2_en=false,.ltf_merge_en=false,.channel_filter_en=false,.manu_scale=false,.shift=0};
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(receive_csi,NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
#if SRASTA_HOTSPOT
    printf("# SRASTA hotspot receiver awaiting association; credentials hidden\n");
    while(!(xEventGroupWaitBits(connection_events,1,pdFALSE,pdTRUE,pdMS_TO_TICKS(1000))&1)) {
        printf("# SRASTA connected=0 disconnect_reason=%u\n",disconnect_reason);
    }
    printf("# SRASTA connected=1\n");
    esp_netif_ip_info_t address;
    ESP_ERROR_CHECK(esp_netif_get_ip_info(station,&address));
    esp_ping_config_t ping_config=ESP_PING_DEFAULT_CONFIG();
    ping_config.target_addr.type=IPADDR_TYPE_V4;
    ping_config.target_addr.u_addr.ip4.addr=address.gw.addr;
    ping_config.count=ESP_PING_COUNT_INFINITE;
    ping_config.interval_ms=1000/SRASTA_RATE_HZ;
    // ESP-IDF waits for a reply before issuing the next request. Bound a lost
    // reply to one traffic interval instead of stalling ten sampling periods.
    ping_config.timeout_ms=ping_config.interval_ms;
    esp_ping_callbacks_t callbacks={.on_ping_success=ping_success,.on_ping_timeout=ping_timeout};
    esp_ping_handle_t ping;
    ESP_ERROR_CHECK(esp_ping_new_session(&ping_config,&callbacks,&ping));
    ESP_ERROR_CHECK(esp_ping_start(ping));
#endif
    frame_t frame;
    int64_t last_diag=0;
    while(1) {
        if(xQueueReceive(frames,&frame,pdMS_TO_TICKS(100))==pdTRUE) emit_frame(&frame);
        int64_t now=esp_timer_get_time();
        if(now-last_diag>1000000) {
            printf("# SRASTA role=RX revision=%s profile=LLTF/HT20/128/imag_real channel=%d rejected=%"PRIu32" queue_dropped=%"PRIu32" observed=%"PRIu64" last_len=%u last_mode=%u stack_low_watermark=%u\n",SRASTA_REVISION,SRASTA_CHANNEL,rejected,dropped,sequence,last_len,last_mode,(unsigned)uxTaskGetStackHighWaterMark(NULL));
#if SRASTA_HOTSPOT
            uint32_t sent=0;
            esp_ping_get_profile(ping,ESP_PING_PROF_REQUEST,&sent,sizeof(sent));
            printf("# SRASTA ping_sent=%"PRIu32" ping_replies=%"PRIu32" ping_timeouts=%"PRIu32" ping_reply_ms=%"PRIu32"\n",sent,ping_replies,ping_timeouts,ping_reply_ms);
#endif
            last_diag=now;
        }
    }
#endif
}
