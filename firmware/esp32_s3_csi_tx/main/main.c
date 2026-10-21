#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <sys/socket.h>
#include <arpa/inet.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_wifi_ap_get_sta_list.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#define TX_SSID "SRASTA_CSI"
#define TX_CHANNEL 6
#define TX_INTERVAL_MS 20
#define TX_PORT 3333

static const char *TAG = "srasta_tx";

/* The password is provisioned over the local USB console and stored in board NVS.
 * It is never compiled into firmware or printed. No RGB LED pattern is used. */
static void load_password(char password[64])
{
    nvs_handle_t handle;
    ESP_ERROR_CHECK(nvs_open("csi_cfg", NVS_READWRITE, &handle));
    size_t size = 64;
    if (nvs_get_str(handle, "tx_pass_v1", password, &size) != ESP_OK) {
        char line[96];
        puts("SRASTA_TX_CONFIG_REQUIRED");
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
                puts("SRASTA_TX_CONFIG_INVALID");
                continue;
            }
            memcpy(password, line + 5, length);
            password[length] = 0;
            ESP_ERROR_CHECK(nvs_set_str(handle, "tx_pass_v1", password));
            ESP_ERROR_CHECK(nvs_commit(handle));
            break;
        }
    }
    nvs_close(handle);
}

static void transmit_task(void *arg)
{
    (void)arg;
    int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) {
        ESP_LOGE(TAG, "UDP socket failed");
        vTaskDelete(NULL);
    }
    uint32_t sequence = 0;
    uint32_t sent = 0;
    uint32_t ticks = 0;
    while (true) {
        wifi_sta_list_t stations = {0};
        wifi_sta_mac_ip_list_t clients = {0};
        if (esp_wifi_ap_get_sta_list(&stations) == ESP_OK &&
            esp_wifi_ap_get_sta_list_with_ip(&stations, &clients) == ESP_OK &&
            clients.num > 0 && clients.sta[0].ip.addr != 0) {
            struct sockaddr_in destination = {
                .sin_family = AF_INET,
                .sin_port = htons(TX_PORT),
                .sin_addr.s_addr = clients.sta[0].ip.addr,
            };
            uint8_t payload[32] = {0};
            memcpy(payload, "SRASTA_TX_V1", 12);
            memcpy(payload + 12, &sequence, sizeof(sequence));
            if (sendto(socket_fd, payload, sizeof(payload), 0,
                       (struct sockaddr *)&destination, sizeof(destination)) == sizeof(payload)) {
                sent++;
            }
            sequence++;
        }
        if (++ticks % 250 == 0) {
            ESP_LOGI(TAG, "channel=%d HT20 clients=%d packets_sent=%lu",
                     TX_CHANNEL, clients.num, (unsigned long)sent);
        }
        vTaskDelay(pdMS_TO_TICKS(TX_INTERVAL_MS));
    }
}

void app_main(void)
{
    esp_err_t nvs_status = nvs_flash_init();
    if (nvs_status == ESP_ERR_NVS_NO_FREE_PAGES || nvs_status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGE(TAG, "NVS requires manual recovery; refusing to erase existing data");
        return;
    }
    ESP_ERROR_CHECK(nvs_status);
    char password[64] = {0};
    load_password(password);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    wifi_config_t config = {0};
    memcpy(config.ap.ssid, TX_SSID, sizeof(TX_SSID) - 1);
    config.ap.ssid_len = sizeof(TX_SSID) - 1;
    memcpy(config.ap.password, password, strlen(password));
    config.ap.channel = TX_CHANNEL;
    config.ap.max_connection = 1;
    config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    config.ap.pmf_cfg.capable = true;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT20));
    memset(password, 0, sizeof(password));
    ESP_LOGI(TAG, "SRASTA TX ready; channel=%d HT20; RGB LED animation disabled", TX_CHANNEL);
    xTaskCreate(transmit_task, "tx_packets", 4096, NULL, 5, NULL);
}
