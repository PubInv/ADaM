// alertService.ts this program is part of the Public Invention Alarm App, it handles playing audio alerts and vibrations based
// on alarm severity and type. It uses the Expo Audio API to play sounds and the React Native Vibration API for haptic feedback.
//
// Copyright (C) 2026  Public Invention.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

import { Vibration } from 'react-native'
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio'
import type { Alarm } from '../types/alarm'

const severitySoundMap = {
  Informational: require('../../assets/Informational.mp3'),
  Problem: require('../../assets/Problem.mp3'),
  Warning: require('../../assets/Warning.mp3'),
  Critical: require('../../assets/Critical.mp3'),
  Panic: require('../../assets/Panic.mp3'),
} as const

const alarmDescriptionSoundMap = {
  FIRE: require('../../assets/AlarmDescriptions/007.mp3'),
  GAS_LEAK: require('../../assets/AlarmDescriptions/009.mp3'),
  LOW_BATTERY: require('../../assets/AlarmDescriptions/023.mp3'),
  GENERATOR_FAULT: require('../../assets/AlarmDescriptions/024.mp3'),
  COMM_LOSS: require('../../assets/AlarmDescriptions/030.mp3'),
  HIGH_TEMPERATURE: require('../../assets/AlarmDescriptions/034.mp3'),
  LOW_TEMPERATURE: require('../../assets/AlarmDescriptions/035.mp3'),
  HIGH_PRESSURE: require('../../assets/AlarmDescriptions/041.mp3'),
  LOW_PRESSURE: require('../../assets/AlarmDescriptions/042.mp3'),
  OVERCURERENT: require('../../assets/AlarmDescriptions/050.mp3'),
  
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