#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#define CSI_LEN 128
#define CSI_CHANNEL 6
#define CSI_INTERVAL_US 20000
#define CONNECTED_BIT BIT0

typedef struct {
    uint32_t sequence;
    int64_t timestamp_us;
    uint8_t mac[6];
    int8_t rssi;
    int8_t noise_floor;
    uint8_t channel;
    uint8_t mcs;
    uint8_t rx_state;
    bool first_word_invalid;
    int8_t iq[CSI_LEN];
} csi_frame_t;

static const char *TAG = "srasta_csi";
static EventGroupHandle_t connected;
static QueueHandle_t frames;
static uint32_t sequence;
static int64_t last_capture_us;
static uint8_t sender_bssid[6];

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(connected, CONNECTED_BIT);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(connected, CONNECTED_BIT);
    }
}

static void csi_callback(void *ctx, wifi_csi_info_t *info)
{
    (void)ctx;
    if (info == NULL || info->buf == NULL || info->len != CSI_LEN ||
        (xEventGroupGetBits(connected) & CONNECTED_BIT) == 0 ||
        memcmp(info->mac, sender_bssid, sizeof(sender_bssid)) != 0 ||
        info->rx_ctrl.channel != CSI_CHANNEL ||
        info->rx_ctrl.sig_mode != 1 || info->rx_ctrl.cwb != 0 || info->rx_ctrl.rx_state != 0) {
        return;
    }
    int64_t now_us = esp_timer_get_time();
    if (now_us - last_capture_us < CSI_INTERVAL_US) {
        return;
    }
    last_capture_us = now_us;
    csi_frame_t frame = {
        .sequence = sequence++,
        .timestamp_us = now_us,
        .rssi = info->rx_ctrl.rssi,
        .noise_floor = info->rx_ctrl.noise_floor,
        .channel = info->rx_ctrl.channel,
        .mcs = info->rx_ctrl.mcs,
        .rx_state = info->rx_ctrl.rx_state,
        .first_word_invalid = info->first_word_invalid,
    };
    memcpy(frame.mac, info->mac, sizeof(frame.mac));
    memcpy(frame.iq, info->buf, CSI_LEN);
    xQueueSend(frames, &frame, 0);
}

static void serial_task(void *arg)
{
    (void)arg;
    csi_frame_t frame;
    char line[1024];
    while (xQueueReceive(frames, &frame, portMAX_DELAY) == pdTRUE) {
        int used = snprintf(line, sizeof(line),
            "{\"version\":1,\"sequence\":%lu,\"local_timestamp_us\":%lld,"
            "\"sender_mac\":\"%02x:%02x:%02x:%02x:%02x:%02x\",\"rssi\":%d,"
            "\"noise_floor\":%d,\"channel\":%u,\"bandwidth\":\"HT20\","
            "\"sig_mode\":\"HT\",\"mcs\":%u,\"rx_state\":%u,\"len\":128,"
            "\"first_word_invalid\":%s,\"iq_bytes\":[",
            (unsigned long)frame.sequence, (long long)frame.timestamp_us,
            frame.mac[0], frame.mac[1], frame.mac[2], frame.mac[3], frame.mac[4], frame.mac[5],
            frame.rssi, frame.noise_floor, frame.channel, frame.mcs, frame.rx_state,
            frame.first_word_invalid ? "true" : "false");
        for (int i = 0; i < CSI_LEN && used > 0 && used < (int)sizeof(line); i++) {
            used += snprintf(line + used, sizeof(line) - used, "%s%d", i ? "," : "", frame.iq[i]);
        }
        if (used > 0 && used < (int)sizeof(line) - 3) {
            memcpy(line + used, "]}\n", 4);
            fwrite(line, 1, used + 3, stdout);
            fflush(stdout);
        }
    }
}

static void configure_capture_channel(void)
{
    EventBits_t bits = xEventGroupWaitBits(
        connected, CONNECTED_BIT, pdFALSE, pdTRUE, pdMS_TO_TICKS(10000));
    if (bits & CONNECTED_BIT) {
        wifi_ap_record_t ap;
        ESP_ERROR_CHECK(esp_wifi_sta_get_ap_info(&ap));
        if (ap.primary != CSI_CHANNEL) {
            ESP_LOGE(TAG, "unexpected TX channel %u", ap.primary);
            abort();
        }
        memcpy(sender_bssid, ap.bssid, sizeof(sender_bssid));
        ESP_LOGI(TAG, "connected to SRASTA TX channel %u; capturing LLTF HT20", ap.primary);
        return;
    }
    ESP_LOGE(TAG, "SRASTA TX unavailable; capture stopped");
    abort();
}

static void read_wifi_config(wifi_config_t *config)
{
    nvs_handle_t nvs;
    ESP_ERROR_CHECK(nvs_open("csi_cfg", NVS_READWRITE, &nvs));
    memcpy(config->sta.ssid, "SRASTA_CSI", sizeof("SRASTA_CSI"));
    size_t password_len = sizeof(config->sta.password);
    if (nvs_get_str(nvs, "rx_pass_v1", (char *)config->sta.password, &password_len) != ESP_OK) {
        char line[96];
        puts("SRASTA_RX_CONFIG_REQUIRED");
        fflush(stdout);
        while (true) {
            if (fgets(line, sizeof(line), stdin) == NULL) {
                vTaskDelay(pdMS_TO_TICKS(100));
                clearerr(stdin);
                continue;
            }
            if (strncmp(line, "CRED ", 5) != 0) {
                continue;
            }
            size_t length = strcspn(line + 5, "\r\n");
            if (length < 8 || length > 63) {
                puts("SRASTA_RX_CONFIG_INVALID");
                continue;
            }
            memcpy(config->sta.password, line + 5, length);
            config->sta.password[length] = 0;
            ESP_ERROR_CHECK(nvs_set_str(nvs, "rx_pass_v1", (char *)config->sta.password));
            ESP_ERROR_CHECK(nvs_commit(nvs));
            break;
        }
    }
    nvs_close(nvs);
}

void app_main(void)
{
    esp_err_t nvs_status = nvs_flash_init();
    if (nvs_status == ESP_ERR_NVS_NO_FREE_PAGES || nvs_status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGE(TAG, "NVS requires manual recovery; refusing to erase existing data");
        return;
    }
    ESP_ERROR_CHECK(nvs_status);
    connected = xEventGroupCreate();
    frames = xQueueCreate(32, sizeof(csi_frame_t));
    if (connected == NULL || frames == NULL) {
        ESP_LOGE(TAG, "failed to allocate runtime queues");
        abort();
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    wifi_config_t config = {0};
    read_wifi_config(&config);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_connect());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    configure_capture_channel();
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20));
    wifi_promiscuous_filter_t filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA,
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    wifi_csi_config_t csi = {
        .lltf_en = true,
        .htltf_en = false,
        .stbc_htltf2_en = false,
        .ltf_merge_en = false,
        .channel_filter_en = false,
        .manu_scale = false,
        .shift = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_callback, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    xTaskCreate(serial_task, "csi_serial", 6144, NULL, 5, NULL);
    ESP_LOGI(TAG, "CSI JSONL ready; model remains on host");
}
