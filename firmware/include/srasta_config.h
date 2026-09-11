#pragma once
// Non-secret defaults. Override in ignored srasta_local.h for a separate pair.
#if __has_include("srasta_local.h")
#include "srasta_local.h"
#endif
#ifndef SRASTA_CHANNEL
#define SRASTA_CHANNEL 1
#endif
#ifndef SRASTA_TX_MAC
#define SRASTA_TX_MAC {0x02,0x00,0x00,0x00,0x00,0x01}
#endif
#ifndef SRASTA_RATE_HZ
#define SRASTA_RATE_HZ 100
#endif
#define SRASTA_REVISION "srasta-jsonl-v1-paced-idf5.4.0"
#if SRASTA_CHANNEL < 1 || SRASTA_CHANNEL > 11
#error "Use a matching permitted 2.4 GHz channel (1..11) on both boards"
#endif
#if SRASTA_RATE_HZ < 1 || SRASTA_RATE_HZ > 100
#error "SRASTA capture target must be between 1 and 100 Hz"
#endif
