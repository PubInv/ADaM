import { Vibration } from 'react-native'
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio'
import type { Alarm } from '../types/alarm'

const severitySoundMap = {
  Informational: require('../../assets/Informational.m4a'),
  Problem: require('../../assets/Problem.m4a'),
  Warning: require('../../assets/Warning.m4a'),
  Critical: require('../../assets/Critical.m4a'),
  Panic: require('../../assets/Panic.m4a'),
} as const

const alarmDescriptionSoundMap = {
  FIRE: require('../../assets/AlarmDescriptions/007.m4a'),
  DOOR_OPEN: require('../../assets/AlarmDescriptions/060.m4a'),
  CPU_OVERLOAD: require('../../assets/AlarmDescriptions/072.m4a'),
  COMM_LOSS: require('../../assets/AlarmDescriptions/030.m4a'),
  DISK_FULL: require('../../assets/AlarmDescriptions/073.m4a'),
  EMERGENCY_STOP: require('../../assets/AlarmDescriptions/062.m4a'),
  FAN_FAILURE: require('../../assets/AlarmDescriptions/075.m4a'),
  GAS_LEAK: require('../../assets/AlarmDescriptions/009.m4a'),
  GENERATOR_FAULT: require('../../assets/AlarmDescriptions/024.m4a'),
  HIGH_PRESSURE: require('../../assets/AlarmDescriptions/041.m4a'),
  HIGH_TEMPERATURE: require('../../assets/AlarmDescriptions/034.m4a'),
  INTRUSION: require('../../assets/AlarmDescriptions/061.m4a'),
  LOW_BATTERY: require('../../assets/AlarmDescriptions/023.m4a'),
  LOW_PRESSURE: require('../../assets/AlarmDescriptions/042.m4a'),
  LOW_TEMPERATURE: require('../../assets/AlarmDescriptions/035.m4a'),
} as const

let player: ReturnType<typeof createAudioPlayer> | null = null

function wait(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export async function prepareAlertAudio() {
  await setAudioModeAsync({
    playsInSilentMode: true,
  })
}

export async function playAlarmAudio(alarm: Alarm, isMuted: boolean) {
  if (isMuted) {
    console.log('Audio blocked because app is muted')
    return
  }

  try {
    console.log('Playing alarm audio for:', alarm)

    Vibration.vibrate()

    const severitySource =
      alarm.severity &&
      severitySoundMap[alarm.severity as keyof typeof severitySoundMap]

    if (severitySource) {
      console.log('Playing severity sound for:', alarm.severity)

      if (player) {
        player.remove()
        player = null
      }

      player = createAudioPlayer(severitySource)
      player.play()

      await wait(1600)
    } else {
      console.log('No severity sound found for:', alarm.severity)
    }

    const descriptionSource =
      alarm.typeCode &&
      alarmDescriptionSoundMap[alarm.typeCode as keyof typeof alarmDescriptionSoundMap]

    if (descriptionSource) {
      console.log('Playing description sound for typeCode:', alarm.typeCode)

      if (player) {
        player.remove()
        player = null
      }

      player = createAudioPlayer(descriptionSource)
      player.play()
    } else {
      console.log('No description sound found for typeCode:', alarm.typeCode)
    }
  } catch (err) {
    console.log('Failed to play alarm audio:', err)
  }
}

export function stopAlarmAudio() {
  Vibration.cancel()

  if (player) {
    player.remove()
    player = null
  }
}