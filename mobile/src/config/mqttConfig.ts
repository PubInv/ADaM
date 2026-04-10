export const mqttConfig = {
  brokerUrl: 'wss://public.cloud.shiftr.io:443',
  username: 'public',
  password: 'public',
  alarmTopic: 'adam/in/alarms',
  ackTopic: 'adam/acks',
  clientId: `adam_mobile_${Math.random().toString(16).slice(2, 10)}`,
  deviceName: 'adam-mobile-1',
}