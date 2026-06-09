/*
 * TrackBot — Low-level motor control for ATmega32U4 (LattePanda Sigma)
 *
 * Protocol (serial, 115200 baud):
 *   INPUT:  "L <speed> R <speed>\n"   speed = -255 .. 255
 *   OUTPUT: "<encL> <encR> <spdL> <spdR>\n"   @ 20Hz
 *
 * Pins:
 *   M1: PWM=9, DIR1=8, DIR2=7, ENCA=2, ENCB=3
 *   M2: PWM=10, DIR1=6, DIR2=5, ENCA=4, ENCB=12
 */

#include <Encoder.h>

// ── Pin assignments ───────────────────────────────────
#define M1_PWM    9
#define M1_DIR1   8
#define M1_DIR2   7
#define M2_PWM    10
#define M2_DIR1   6
#define M2_DIR2   5

#define M1_ENCA   2
#define M1_ENCB   3
#define M2_ENCA   4
#define M2_ENCB   12

// ── Constants ─────────────────────────────────────────
#define BAUD        115200
#define CTRL_HZ     100
#define REPORT_HZ   20
#define ENCODER_PPR 48
#define PWM_RANGE   255
#define DEADBAND    15

#define SERIAL_BUF  32

// ── Global state ──────────────────────────────────────
Encoder encLeft(M1_ENCA, M1_ENCB);
Encoder encRight(M2_ENCA, M2_ENCB);

int16_t targetSpeedL = 0;
int16_t targetSpeedR = 0;
int16_t currentSpeedL = 0;
int16_t currentSpeedR = 0;

long lastEncL = 0;
long lastEncR = 0;
unsigned long lastCtrlUs = 0;
unsigned long lastReportMs = 0;

// PID state
float kp = 1.0, ki = 0.1, kd = 0.05;
float integralL = 0, integralR = 0;
int lastErrorL = 0, lastErrorR = 0;
const float integralLimit = 200;

// ── Command buffer ────────────────────────────────────
char serialBuf[SERIAL_BUF];
uint8_t serialIdx = 0;

// ── Forward declarations ──────────────────────────────
void parseCommand();
void setMotor(int pwm, int dir1, int dir2, int16_t speed);
void controlLoop();
void reportState();

// ── Setup ─────────────────────────────────────────────
void setup() {
  pinMode(M1_PWM, OUTPUT);
  pinMode(M1_DIR1, OUTPUT);
  pinMode(M1_DIR2, OUTPUT);
  pinMode(M2_PWM, OUTPUT);
  pinMode(M2_DIR1, OUTPUT);
  pinMode(M2_DIR2, OUTPUT);

  setMotor(M1_PWM, M1_DIR1, M1_DIR2, 0);
  setMotor(M2_PWM, M2_DIR1, M2_DIR2, 0);

  Serial.begin(BAUD);
  while (!Serial) { delay(10); }

  // Timer1 for PWM on pins 9,10 at 5kHz
  TCCR1A = _BV(WGM10) | _BV(WGM11);
  TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS11);
  ICR1 = 400;

  lastCtrlUs = micros();
  lastReportMs = millis();
}

// ── Main loop ─────────────────────────────────────────
void loop() {
  // Read serial
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || serialIdx >= SERIAL_BUF - 1) {
      serialBuf[serialIdx] = '\0';
      parseCommand();
      serialIdx = 0;
    } else if (c != '\r') {
      serialBuf[serialIdx++] = c;
    }
  }

  // 100Hz control loop
  unsigned long now = micros();
  if (now - lastCtrlUs >= 10000) {
    controlLoop();
    lastCtrlUs = now;
  }

  // 20Hz state report
  unsigned long nowMs = millis();
  if (nowMs - lastReportMs >= 50) {
    reportState();
    lastReportMs = nowMs;
  }
}

// ── Parse "L <speed> R <speed>" ────────────────────────
void parseCommand() {
  char *p = serialBuf;
  while (*p == ' ') p++;

  if (p[0] == 'L' && p[1] == ' ') {
    int val = atoi(p + 2);
    targetSpeedL = constrain(val, -PWM_RANGE, PWM_RANGE);
  } else if (p[0] == 'R' && p[1] == ' ') {
    int val = atoi(p + 2);
    targetSpeedR = constrain(val, -PWM_RANGE, PWM_RANGE);
  }

  // Handle "L ... R ..." on one line
  char *r = strstr(p, " R ");
  if (r) {
    int val = atoi(r + 3);
    targetSpeedR = constrain(val, -PWM_RANGE, PWM_RANGE);
  }
}

// ── Set motor speed (-255..255) ────────────────────────
void setMotor(int pwm, int dir1, int dir2, int16_t speed) {
  if (speed > DEADBAND) {
    digitalWrite(dir1, HIGH);
    digitalWrite(dir2, LOW);
    analogWrite(pwm, speed);
  } else if (speed < -DEADBAND) {
    digitalWrite(dir1, LOW);
    digitalWrite(dir2, HIGH);
    analogWrite(pwm, -speed);
  } else {
    digitalWrite(dir1, LOW);
    digitalWrite(dir2, LOW);
    analogWrite(pwm, 0);
  }
}

// ── PID velocity control (100Hz) ──────────────────────
void controlLoop() {
  long nowEncL = encLeft.read();
  long nowEncR = encRight.read();
  long deltaL = nowEncL - lastEncL;
  long deltaR = nowEncR - lastEncR;
  lastEncL = nowEncL;
  lastEncR = nowEncR;

  // Speed in encoder ticks per 100Hz tick (scaled to -255..255 range)
  currentSpeedL = constrain(deltaL * 2, -PWM_RANGE, PWM_RANGE);
  currentSpeedR = constrain(deltaR * 2, -PWM_RANGE, PWM_RANGE);

  // PID compute
  int errorL = targetSpeedL - currentSpeedL;
  int errorR = targetSpeedR - currentSpeedR;

  integralL += errorL * 0.1;
  integralR += errorR * 0.1;
  integralL = constrain(integralL, -integralLimit, integralLimit);
  integralR = constrain(integralR, -integralLimit, integralLimit);

  float derivL = (errorL - lastErrorL);
  float derivR = (errorR - lastErrorR);
  lastErrorL = errorL;
  lastErrorR = errorR;

  int16_t outL = (int16_t)(kp * errorL + ki * integralL + kd * derivL);
  int16_t outR = (int16_t)(kp * errorR + ki * integralR + kd * derivR);

  setMotor(M1_PWM, M1_DIR1, M1_DIR2, outL);
  setMotor(M2_PWM, M2_DIR1, M2_DIR2, outR);
}

// ── Report state to serial (20Hz) ─────────────────────
void reportState() {
  Serial.print(encLeft.read());
  Serial.print(' ');
  Serial.print(encRight.read());
  Serial.print(' ');
  Serial.print(currentSpeedL);
  Serial.print(' ');
  Serial.print(currentSpeedR);
  Serial.print(' ');
  Serial.print(targetSpeedL);
  Serial.print(' ');
  Serial.println(targetSpeedR);
}
