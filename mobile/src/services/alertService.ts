import { Vibration } from 'react-native'
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio'
import * as Speech from 'expo-speech'
import type { Alarm} from '../types/alarm'

let alarmPlayer: ReturnType<typeof createAudioPlayer> | null = null

const severityLabels: Record<number, string> = {
    1: 'Informational',
    2: 'Problem',
    3: 'Warning',
    4: 'Critical',
    5: 'Panic',
}

function getSeverityLabel(severity?: string): string {
  if (!severity) return 'Unknown severity'

  const trimmed = severity.trim()

  const numericValue = Number(trimmed)
  if (!Number.isNaN(numericValue) && severityLabels[numericValue]) {
    return severityLabels[numericValue]
  }

  const normalized = trimmed.toLowerCase()

  if (normalized === 'informational') return 'Informational'
  if (normalized === 'problem') return 'Problem'
  if (normalized === 'warning') return 'Warning'
  if (normalized === 'critical') return 'Critical'
  if (normalized === 'panic') return 'Panic'

  return trimmed
}

function buildAlarmSpeechText(alarm: Alarm): string {
  const severityLabel = getSeverityLabel(alarm.severity)
  const message = alarm.message?.trim() || 'No message provided'

  return `${severityLabel}. ${message}.`
}

export async function triggerAlarmAnnouncement(alarm: Alarm, isMuted: boolean) {
  if (isMuted) return

  try {
    Vibration.vibrate()

    const speechText = buildAlarmSpeechText(alarm)

    Speech.stop()
    Speech.speak(speechText, {
      language: 'en',
      pitch: 1.0,
      rate: 0.95,
    })
  } catch (err) {
    console.log('Failed to announce alarm:', err)
  }
}

export function stopAlarmAnnouncement() {
  Vibration.cancel()
  Speech.stop()
}

export async function loadAlarmSound()
{
    if (alarmPlayer) return

    await setAudioModeAsync({playsInSilentMode: true,})

    alarmPlayer = createAudioPlayer(require('../../assets/medium1.mp3'))

}

export async function triggerAlarmAlert(isMuted: boolean)
{
    try {
        if (isMuted) return

        Vibration.vibrate()

        if (alarmPlayer)
        {
            alarmPlayer.seekTo(0)
            alarmPlayer.play()
        }
    } catch (err)
    {
        console.log('Failed to trigger alarm alert', err)
    }
}

export function stopAlarmAlert()
{
    try {
        Vibration.cancel()

        if(alarmPlayer && alarmPlayer.playing)
        {
            alarmPlayer.pause()
            alarmPlayer.seekTo(0)
        }
    }catch (err)
    {
        console.log('Failed to stop alarm alert:', err)
    }
}

export function cleanupAlarmSound() {
    if (alarmPlayer) {
        alarmPlayer.remove()
        alarmPlayer = null
    }
}