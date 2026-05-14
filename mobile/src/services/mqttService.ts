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
  const severityMatch = payload.match(/^a(\d+)/i)
  const idMatch = payload.match(/\{([^}]+)\}/)
  const typeMatch = payload.match(/TYPE:([A-Z0-9_]+)/i)

  const severityNumber = severityMatch?.[1]
  const alarmId = idMatch?.[1]
  const alarmType = typeMatch?.[1]

  const formattedMessage = alarmType
    ? alarmType
        .replace(/_/g, ' ')
        .toLowerCase()
        .replace(/\b\w/g, char => char.toUpperCase())
    : payload
  return {
    id: alarmId ?? '',
    typeCode: alarmType ?? '',
    severity: getSeverityLabel(severityNumber),
    message: formattedMessage,
    timestamp: new Date().toISOString(),
    raw: payload,
  }

  

}

const buildActionMessage = (action: string, alarm?: Alarm): string => {
  const severityCode =
    alarm?.severity === 'Informational' ? '1' :
    alarm?.severity === 'Problem' ? '2' :
    alarm?.severity === 'Warning' ? '3' :
    alarm?.severity === 'Critical' ? '4' :
    alarm?.severity === 'Panic' ? '5' :
    '0'

  const alarmId = alarm?.id ?? 'UNKNOWN'
  const messageType = alarm?.message
    ? alarm.message.toUpperCase().replace(/\s+/g, '_')
    : 'UNKNOWN'

  return `ACTION:${action.toUpperCase()};SEVERITY:${severityCode};ID:${alarmId};TYPE:${messageType}`
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

  const payload = buildActionMessage(action, alarm)

  client.publish(mqttConfig.ackTopic, payload)
}

export const disconnectMqtt = () => {
  if (client) {
    client.end(true)
    client = null
  }
}