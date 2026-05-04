import mqtt, { MqttClient } from 'mqtt'
import { mqttConfig } from '../config/mqttConfig'
import { Alarm } from '../types/alarm'

let client: MqttClient | null = null

const getSeverityLabel = (value: unknown): string => {
  if (value === null || value === undefined) return 'unknown'

  const stringValue = String(value).trim().toLowerCase()

  if (stringValue === '1') return 'Informational'
  if (stringValue === '2') return 'Problem'
  if (stringValue === '3') return 'Warning'
  if (stringValue === '4') return 'Critical'
  if (stringValue === '5') return 'Panic'

  if (stringValue === 'informational') return 'Informational'
  if (stringValue === 'problem') return 'Problem'
  if (stringValue === 'warning') return 'Warning'
  if (stringValue === 'critical') return 'Critical'
  if (stringValue === 'panic') return 'Panic'

  return 'unknown'
}

const parseAlarmMessage = (payload: string): Alarm => {
  try {
    console.log('Raw alarm payload:', payload)
    const data = JSON.parse(payload)
    console.log('Incoming alarm data:', data)
    return {
      id: data.id ?? data.alarm_id ?? data.uuid ?? '',
      severity: getSeverityLabel(data.severity ?? data.priority ?? data.level),
      message: data.message ?? data.text ?? data.description ?? payload,
      timestamp: data.timestamp ?? new Date().toISOString(),
      raw: payload,
    }
    
  } catch {
    return {
      message: payload,
      severity: 'unknown',
      timestamp: new Date().toISOString(),
      raw: payload,
    }
  }

  
}

export const connectMqtt = ({
  onConnect,
  onDisconnect,
  onError,
  onAlarm,
}: {
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: string) => void
  onAlarm?: (alarm: Alarm) => void
}) => {
  if (client?.connected) return client

  client = mqtt.connect(mqttConfig.brokerUrl, {
    username: mqttConfig.username,
    password: mqttConfig.password,
    clientId: mqttConfig.clientId,
    clean: true,
    reconnectPeriod: 3000,
    connectTimeout: 10000,
  })

  client.on('connect', () => {
    onConnect?.()

    client?.subscribe(mqttConfig.alarmTopic, (err) => {
      if (err) {
        onError?.(`Subscribe failed: ${err.message}`)
      }
    })
  })

  client.on('message', (topic, message) => {
    if (topic !== mqttConfig.alarmTopic) return

    const payload = message.toString()
    const alarm = parseAlarmMessage(payload)
    onAlarm?.(alarm)
  })

  client.on('close', () => {
    onDisconnect?.()
  })

  client.on('error', (err) => {
    onError?.(err.message)
  })

  return client
}

export const publishAction = (action: string, alarm?: Alarm) => {
  if (!client || !client.connected) {
    throw new Error('MQTT client is not connected')
  }

  const payload = {
    action,
    alarm_id: alarm?.id ?? '',
    device: mqttConfig.deviceName,
    timestamp: new Date().toISOString(),
    source: 'mobile',
    message: alarm?.message ?? '',
  }

  client.publish(mqttConfig.ackTopic, JSON.stringify(payload))
}

export const disconnectMqtt = () => {
  if (client) {
    client.end(true)
    client = null
  }
}