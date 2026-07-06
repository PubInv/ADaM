export const mqttConfig = {
  brokerUrl: process.env.EXPO_PUBLIC_BROKER_URL ?? 'wss://public.cloud.shiftr.io:443',
  username: process.env.EXPO_PUBLIC_BROKER_USERNAME ?? 'public',
  password: process.env.EXPO_PUBLIC_BROKER_PASSWORD ?? 'public',
  alarmTopic: 'adam/in/alarms',
  ackTopic: 'adam/acks',
  clientId: `adam_mobile_${Math.random().toString(16).slice(2, 10)}`,
  deviceName: 'adam-mobile-1',
}