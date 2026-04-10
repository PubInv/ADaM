import mqtt, { MqttClient } from 'mqtt'
import { mqttConfig } from '../config/mqttConfig'
import { Alarm } from '../types/alarm'

let client: MqttClient | null = null

const parseAlarmMessage = (payload: string): Alarm => {
  try {
    const data = JSON.parse(payload)

    return {
      id: data.id ?? data.alarm_id ?? data.uuid ?? '',
      severity: data.severity ?? data.priority ?? 'unknown',
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