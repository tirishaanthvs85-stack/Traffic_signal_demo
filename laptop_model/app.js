/**
 * NEURA-TRAFFIC AI 4.0 - Autonomous Urban Grid Controller
 * Complete Working Laptop Model & Interactive Demonstration Deck
 */

(function () {
  'use strict';

  // =========================================================================
  // 1. DATA MODELS & ENUMS
  // =========================================================================
  const Direction = {
    NORTH: 'North',
    SOUTH: 'South',
    EAST: 'East',
    WEST: 'West'
  };

  const LightState = {
    RED: 'RED',
    YELLOW: 'YELLOW',
    GREEN: 'GREEN'
  };

  const VehicleType = {
    CAR: { name: 'Car', priority: 1.0, length: 26, width: 14, color: '#38bdf8', weight: 1.0 },
    BUS: { name: 'Bus', priority: 2.2, length: 48, width: 17, color: '#f59e0b', weight: 2.5 },
    TRUCK: { name: 'Truck', priority: 2.0, length: 42, width: 16, color: '#f97316', weight: 2.0 },
    BIKE: { name: 'Motorbike', priority: 0.6, length: 16, width: 8, color: '#a855f7', weight: 0.5 },
    AMBULANCE: { name: 'Ambulance', priority: 15.0, length: 30, width: 15, color: '#ffffff', weight: 10.0 }
  };

  class Vehicle {
    static idCounter = 0;
    constructor(direction, type = null) {
      this.id = ++Vehicle.idCounter;
      this.direction = direction;
      this.type = type || this.randomType();
      this.pos = 0; // Distance along lane from entry (pixels)
      this.speed = 0;
      this.maxSpeed = this.type === VehicleType.AMBULANCE ? 4.2 : (2.2 + Math.random() * 0.8);
      this.isEmergency = this.type === VehicleType.AMBULANCE;
      this.waitTime = 0;
      this.isStopped = false;
      this.cleared = false;

      // Turning Intent: 35% Turn Right, 30% Turn Left, 35% Straight
      const r = Math.random();
      if (this.isEmergency) {
        this.turnIntent = r < 0.6 ? 'straight' : (r < 0.8 ? 'left' : 'right');
      } else {
        this.turnIntent = r < 0.35 ? 'straight' : (r < 0.68 ? 'left' : 'right');
      }
      this.blinkerTick = 0;
    }

    randomType() {
      const r = Math.random();
      if (r < 0.65) return VehicleType.CAR;
      if (r < 0.80) return VehicleType.BIKE;
      if (r < 0.90) return VehicleType.BUS;
      if (r < 0.98) return VehicleType.TRUCK;
      return VehicleType.AMBULANCE;
    }
  }

  // =========================================================================
  // 2. AUDIO SYNTHESIZER (WEB AUDIO API - ZERO EXTERNAL ASSETS REQUIRED)
  // =========================================================================
  class SoundFX {
    constructor() {
      this.ctx = null;
      this.enabled = true;
      this.sirenOsc = null;
      this.sirenGain = null;
      this.isSirenPlaying = false;
    }

    init() {
      if (!this.ctx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) this.ctx = new AudioCtx();
      }
      if (this.ctx && this.ctx.state === 'suspended') {
        this.ctx.resume();
      }
    }

    playChime(type = 'green') {
      if (!this.enabled) return;
      this.init();
      if (!this.ctx) return;

      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);

      const now = this.ctx.currentTime;
      if (type === 'green') {
        osc.frequency.setValueAtTime(587.33, now); // D5
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      } else if (type === 'yellow') {
        osc.frequency.setValueAtTime(440, now);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      } else if (type === 'cutoff') {
        osc.frequency.setValueAtTime(783.99, now); // G5
        osc.frequency.exponentialRampToValueAtTime(1046.50, now + 0.1); // C6
        gain.gain.setValueAtTime(0.07, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      }
      osc.start(now);
      osc.stop(now + 0.35);
    }

    startSiren() {
      if (!this.enabled || this.isSirenPlaying) return;
      this.init();
      if (!this.ctx) return;

      this.isSirenPlaying = true;
      this.sirenOsc = this.ctx.createOscillator();
      this.sirenGain = this.ctx.createGain();
      this.sirenOsc.type = 'sawtooth';

      const now = this.ctx.currentTime;
      this.sirenGain.gain.setValueAtTime(0.08, now);

      // Ambulance dual-tone oscillation
      this.sirenOsc.frequency.setValueAtTime(650, now);
      let high = true;
      this.sirenInterval = setInterval(() => {
        if (!this.ctx || !this.sirenOsc) return;
        const t = this.ctx.currentTime;
        this.sirenOsc.frequency.linearRampToValueAtTime(high ? 900 : 650, t + 0.2);
        high = !high;
      }, 350);

      this.sirenOsc.connect(this.sirenGain);
      this.sirenGain.connect(this.ctx.destination);
      this.sirenOsc.start();
    }

    stopSiren() {
      if (!this.isSirenPlaying) return;
      if (this.sirenInterval) clearInterval(this.sirenInterval);
      if (this.sirenGain && this.ctx) {
        this.sirenGain.gain.linearRampToValueAtTime(0.001, this.ctx.currentTime + 0.2);
        setTimeout(() => {
          if (this.sirenOsc) {
            try { this.sirenOsc.stop(); } catch(e){}
            this.sirenOsc.disconnect();
          }
          this.isSirenPlaying = false;
        }, 220);
      } else {
        this.isSirenPlaying = false;
      }
    }
  }

  // =========================================================================
  // 3. AI ADAPTIVE TRAFFIC CONTROLLER
  // =========================================================================
  class AITrafficController {
    constructor() {
      this.mode = 'AI_DYNAMIC'; // 'AI_DYNAMIC' or 'FIXED'
      this.activeDirection = Direction.NORTH;
      this.phaseType = 'GREEN'; // 'GREEN' or 'YELLOW'
      this.phaseTimer = 14.0;
      this.allocatedGreen = 14.0;
      this.yellowDuration = 3.0;
      this.emergencyActive = false;
      this.emergencyDirection = null;
      this.resumingDirection = null;

      // Exactly ONE direction is GREEN (or YELLOW) at any moment; all other 3 are RED!
      this.lights = {
        [Direction.NORTH]: LightState.GREEN,
        [Direction.SOUTH]: LightState.RED,
        [Direction.EAST]: LightState.RED,
        [Direction.WEST]: LightState.RED
      };

      this.stats = {
        vehiclesCleared: 0,
        totalWaitAccumulator: 0,
        completedVehicleCount: 0,
        emergencyPreemptions: 0,
        earlyCutoffs: 0,
        phaseSwitches: 0
      };

      // Configuration constants
      this.MIN_GREEN = 7.0;
      this.MAX_GREEN = 32.0;
      this.BASE_TIME = 6.0;
      this.ALPHA_QUEUE = 2.0;
      this.BETA_WEIGHT = 2.5;
      this.FIXED_GREEN = 16.0;
    }

    get activePhase() {
      return `${this.activeDirection.toUpperCase()}_${this.phaseType}`;
    }

    setMode(mode) {
      this.mode = mode;
      this.log(`Switched control mode to [${mode === 'AI_DYNAMIC' ? 'AI Dynamic Single-Signal (Protected Turns)' : 'Fixed 16s Cycle'}]`);
    }

    update(dt, simulation) {
      this.phaseTimer -= dt;

      // Check for emergency vehicle on any approach
      const emergencyLane = simulation.getEmergencyApproach();
      if (emergencyLane && !this.emergencyActive) {
        this.triggerEmergencyPreemption(emergencyLane);
      }

      // Check for early cutoff in AI Dynamic mode (when active green lane has emptied)
      if (this.mode === 'AI_DYNAMIC' && !this.emergencyActive && this.isGreenPhase()) {
        const activeQueue = simulation.getApproachQueue(this.activeDirection);
        const elapsedGreen = this.allocatedGreen - this.phaseTimer;
        // If queue has drained and minimum clearance has elapsed, cut off early
        if (activeQueue === 0 && elapsedGreen >= this.MIN_GREEN && this.phaseTimer > 2.0) {
          this.stats.earlyCutoffs++;
          this.log(`⚡ Early Cutoff: ${this.activeDirection} queue cleared in ${elapsedGreen.toFixed(1)}s (Saved ${(this.phaseTimer).toFixed(1)}s)`);
          window.TrafficApp.showCutoffPill();
          window.TrafficApp.audio.playChime('cutoff');
          this.phaseTimer = 0.1; // trigger switch to yellow immediately
        }
      }

      // Normal phase expiration
      if (this.phaseTimer <= 0) {
        this.advancePhase(simulation);
      }
    }

    isGreenPhase() {
      return this.phaseType === 'GREEN';
    }

    getActiveApproach() {
      return this.activeDirection;
    }

    advancePhase(simulation) {
      this.stats.phaseSwitches++;

      if (this.emergencyActive) {
        // Emergency corridor has completed clearance
        this.emergencyActive = false;
        window.TrafficApp.hideEmergencyBanner();
        window.TrafficApp.audio.stopSiren();
        this.log(`Emergency vehicle cleared intersection. Resuming standard protected turn schedule.`);
        this.activeDirection = this.resumingDirection || Direction.NORTH;
        this.phaseType = 'YELLOW';
        this.phaseTimer = this.yellowDuration;
        this.updateLights();
        return;
      }

      if (this.phaseType === 'GREEN') {
        // Active single signal cycles to YELLOW before next direction gets GREEN
        this.phaseType = 'YELLOW';
        this.phaseTimer = this.yellowDuration;
        window.TrafficApp.audio.playChime('yellow');
        this.updateLights();
      } else {
        // YELLOW expired -> Pick NEXT single direction to turn GREEN
        const nextDir = this.pickNextDirection(simulation);
        this.activeDirection = nextDir;
        this.phaseType = 'GREEN';
        this.calculateAndSetGreen(nextDir, simulation);
        window.TrafficApp.audio.playChime('green');
        this.updateLights();
      }
    }

    pickNextDirection(simulation) {
      const order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST];
      if (this.mode === 'FIXED') {
        const currIdx = order.indexOf(this.activeDirection);
        return order[(currIdx + 1) % order.length];
      }

      // AI Adaptive selection: score each candidate approach
      const candidates = order.filter(d => d !== this.activeDirection);
      let bestDir = candidates[0];
      let bestScore = -1;

      for (const d of candidates) {
        const m = simulation.getApproachMetrics(d);
        // Urgency score: (Queue * 2.0) + (Heavy Transit * 2.5) + (MaxWait * 0.6)
        let score = (m.queueCount * 2.0) + (m.transitWeight * 2.5) + (m.maxWaitTime * 0.6);
        // Starvation prevention boost if waiting over 25 seconds
        if (m.maxWaitTime > 25.0) {
          score += 25.0 + (m.maxWaitTime - 25.0) * 1.5;
        }
        if (m.hasEmergency) {
          score += 500.0;
        }
        if (score > bestScore) {
          bestScore = score;
          bestDir = d;
        }
      }

      // If all queues are empty, proceed round-robin
      if (bestScore <= 0) {
        const currIdx = order.indexOf(this.activeDirection);
        return order[(currIdx + 1) % order.length];
      }

      return bestDir;
    }

    calculateAndSetGreen(direction, simulation) {
      if (this.mode === 'FIXED') {
        this.allocatedGreen = this.FIXED_GREEN;
        this.phaseTimer = this.FIXED_GREEN;
        return;
      }

      // Dynamic green calculation for the single approach
      const data = simulation.getApproachMetrics(direction);
      const queueCount = data.queueCount;
      const busWeight = data.transitWeight;
      const maxWait = data.maxWaitTime;

      let calculated = this.BASE_TIME + (queueCount * this.ALPHA_QUEUE) + (busWeight * this.BETA_WEIGHT);

      if (maxWait > 25.0) {
        calculated += Math.min(8.0, (maxWait - 25.0) * 0.5);
      }

      const finalGreen = Math.min(this.MAX_GREEN, Math.max(this.MIN_GREEN, calculated));
      this.allocatedGreen = Math.round(finalGreen * 10) / 10;
      this.phaseTimer = this.allocatedGreen;

      this.log(`AI Allocated Single Green [${direction}]: ${this.allocatedGreen}s (Queue: ${queueCount}, MaxWait: ${maxWait.toFixed(1)}s, Left/Right turns protected)`);
    }

    triggerEmergencyPreemption(emergencyDirection) {
      this.emergencyActive = true;
      this.emergencyDirection = emergencyDirection;
      this.stats.emergencyPreemptions++;

      this.log(`🚨 EMERGENCY PREEMPTION: Ambulance on ${emergencyDirection} Approach. Opening exclusive single GREEN signal!`);
      window.TrafficApp.showEmergencyBanner(emergencyDirection);
      window.TrafficApp.audio.startSiren();

      if (this.activeDirection === emergencyDirection && this.phaseType === 'GREEN') {
        this.phaseTimer = Math.max(this.phaseTimer, 15.0);
        this.allocatedGreen = 15.0;
      } else {
        this.resumingDirection = this.activeDirection;
        this.activeDirection = emergencyDirection;
        this.phaseType = 'GREEN';
        this.phaseTimer = 16.0;
        this.allocatedGreen = 16.0;
        this.updateLights();
      }
    }

    updateLights() {
      // Exactly ONE direction gets GREEN or YELLOW. ALL other 3 directions are RED!
      for (const d of Object.values(Direction)) {
        if (d === this.activeDirection) {
          this.lights[d] = (this.phaseType === 'GREEN') ? LightState.GREEN : LightState.YELLOW;
        } else {
          this.lights[d] = LightState.RED;
        }
      }
    }

    recordClearedVehicle(wait) {
      this.stats.vehiclesCleared++;
      this.stats.totalWaitAccumulator += wait;
      this.stats.completedVehicleCount++;
    }

    getAvgWaitTime() {
      if (this.stats.completedVehicleCount === 0) return 0;
      return this.stats.totalWaitAccumulator / this.stats.completedVehicleCount;
    }

    log(msg) {
      if (window.TrafficApp && window.TrafficApp.addLogEntry) {
        window.TrafficApp.addLogEntry(msg);
      }
    }
  }

  // =========================================================================
  // 4. INTERSECTION TRAFFIC SIMULATION & KINEMATICS
  // =========================================================================
  class TrafficSimulation {
    constructor(controller) {
      this.controller = controller;
      this.vehicles = {
        [Direction.NORTH]: [],
        [Direction.SOUTH]: [],
        [Direction.EAST]: [],
        [Direction.WEST]: []
      };

      this.spawnTimer = 0;
      this.spawnRate = 1.4; // seconds between vehicle generation
      this.autoSpawn = true;
      this.rainDrops = [];
      this.isRaining = false;
      this.initRain();

      // Geometry coordinates
      this.roadWidth = 140;
      this.stopLineDist = 260; // Pixels from canvas entry to stop line
      this.intersectionEnd = 440; // Pixels when fully cleared
    }

    initRain() {
      this.rainDrops = [];
      for (let i = 0; i < 80; i++) {
        this.rainDrops.push({
          x: Math.random() * 700,
          y: Math.random() * 700,
          len: 10 + Math.random() * 12,
          speed: 8 + Math.random() * 6
        });
      }
    }

    spawnVehicle(direction, type = null) {
      const lane = this.vehicles[direction];
      // Check if entry position is clear
      if (lane.length > 0 && lane[lane.length - 1].pos < 40) {
        return; // Lane entry blocked
      }
      lane.push(new Vehicle(direction, type));
    }

    spawnEmergency(direction) {
      this.spawnVehicle(direction, VehicleType.AMBULANCE);
      this.controller.log(`🚑 Dispatched Emergency Ambulance on ${direction} Approach!`);
    }

    injectBurst(corridor) {
      if (corridor === 'NorthSouth' || corridor === 'All') {
        for (let i = 0; i < 4; i++) {
          setTimeout(() => {
            this.spawnVehicle(Direction.NORTH);
            this.spawnVehicle(Direction.SOUTH);
          }, i * 350);
        }
      }
      if (corridor === 'EastWest' || corridor === 'All') {
        for (let i = 0; i < 4; i++) {
          setTimeout(() => {
            this.spawnVehicle(Direction.EAST);
            this.spawnVehicle(Direction.WEST);
          }, i * 350);
        }
      }
      this.controller.log(`💥 Injected Traffic Burst into [${corridor}] Corridor`);
    }

    update(dt) {
      // Auto vehicle spawning
      if (this.autoSpawn) {
        this.spawnTimer += dt;
        if (this.spawnTimer >= this.spawnRate) {
          this.spawnTimer = 0;
          const dirs = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST];
          const chosenDir = dirs[Math.floor(Math.random() * dirs.length)];
          this.spawnVehicle(chosenDir);
        }
      }

      // Update vehicle positions and physics
      for (const d of Object.values(Direction)) {
        const lane = this.vehicles[d];
        const light = this.controller.lights[d];

        for (let i = 0; i < lane.length; i++) {
          const v = lane[i];
          const leadVehicle = i > 0 ? lane[i - 1] : null;

          // Determine target stop position
          let targetStop = Infinity;

          // Stop at lead vehicle
          if (leadVehicle) {
            targetStop = leadVehicle.pos - (v.type.length / 2 + leadVehicle.type.length / 2 + 10);
          }

          // Stop at traffic light stopline if red or yellow
          if (v.pos < this.stopLineDist) {
            if (light === LightState.RED || (light === LightState.YELLOW && v.pos < this.stopLineDist - 40)) {
              // If emergency vehicle has green preemption, it doesn't stop
              targetStop = Math.min(targetStop, this.stopLineDist - (v.type.length / 2 + 4));
            }
          }

          const distToStop = targetStop - v.pos;

          if (distToStop <= 0) {
            // Completely stopped
            v.speed = 0;
            v.isStopped = true;
            v.waitTime += dt;
          } else if (distToStop < 40) {
            // Decelerating smoothly
            v.speed = Math.max(0.2, (distToStop / 40) * v.maxSpeed);
            v.isStopped = false;
          } else {
            // Cruising or accelerating
            v.speed = Math.min(v.maxSpeed, v.speed + 1.2 * dt);
            v.isStopped = false;
          }

          v.pos += v.speed * 30 * dt;

          // Check if vehicle has cleared intersection
          if (v.pos >= 720) {
            v.cleared = true;
            this.controller.recordClearedVehicle(v.waitTime);
          }
        }

        // Clean up cleared vehicles
        this.vehicles[d] = lane.filter(v => !v.cleared);
      }

      // Update rain
      if (this.isRaining) {
        for (const drop of this.rainDrops) {
          drop.y += drop.speed;
          drop.x -= 1.5;
          if (drop.y > 700) drop.y = -10;
          if (drop.x < 0) drop.x = 700;
        }
      }
    }

    getEmergencyApproach() {
      for (const d of Object.values(Direction)) {
        for (const v of this.vehicles[d]) {
          if (v.isEmergency && v.pos < this.intersectionEnd) {
            return d;
          }
        }
      }
      return null;
    }

    getApproachQueue(direction) {
      let count = 0;
      for (const v of this.vehicles[direction]) {
        if (v.pos <= this.stopLineDist + 15) count++;
      }
      return count;
    }

    getApproachMetrics(direction) {
      let queueCount = 0;
      let transitWeight = 0;
      let maxWaitTime = 0;
      let hasEmergency = false;

      for (const v of this.vehicles[direction]) {
        if (v.pos <= this.stopLineDist + 20) {
          queueCount++;
          if (v.type === VehicleType.BUS || v.type === VehicleType.TRUCK) {
            transitWeight += v.type.weight;
          }
          if (v.waitTime > maxWaitTime) {
            maxWaitTime = v.waitTime;
          }
          if (v.isEmergency) {
            hasEmergency = true;
          }
        }
      }

      return { queueCount, transitWeight, maxWaitTime, hasEmergency };
    }

    getActiveCorridorQueue(corridor) {
      return this.getApproachQueue(corridor);
    }

    getCorridorMetrics(corridor) {
      return this.getApproachMetrics(corridor);
    }
  }

  // =========================================================================
  // 5. COMPUTER VISION & PERCEPTION SENSOR (WEBCAM & SYNTHETIC CCTV)
  // =========================================================================
  class VisionPerceptionSensor {
    constructor(canvas, videoElement) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.video = videoElement;
      this.mode = 'CCTV'; // 'CCTV' or 'WEBCAM'
      this.stream = null;
      this.frameCount = 0;
      this.motionDetections = [];
      this.lastFrameData = null;

      // Synthetic traffic CCTV state
      this.cctvVehicles = [
        { id: 1, x: 280, y: 40, dx: 0, dy: 1.8, w: 26, h: 48, type: 'Bus', color: '#f59e0b', roi: 'NORTH' },
        { id: 2, x: 330, y: 110, dx: 0, dy: 2.2, w: 22, h: 40, type: 'Car', color: '#38bdf8', roi: 'NORTH' },
        { id: 3, x: 280, y: 350, dx: 0, dy: -2.0, w: 22, h: 40, type: 'Car', color: '#ffffff', roi: 'SOUTH' },
        { id: 4, x: 540, y: 175, dx: -2.4, dy: 0, w: 42, h: 22, type: 'Truck', color: '#f97316', roi: 'EAST' },
        { id: 5, x: 470, y: 205, dx: -2.1, dy: 0, w: 38, h: 22, type: 'Car', color: '#10b981', roi: 'EAST' },
        { id: 6, x: 80, y: 190, dx: 2.6, dy: 0, w: 24, h: 14, type: 'Bike', color: '#a855f7', roi: 'WEST' }
      ];

      // Quadrant ROIs
      this.rois = {
        NORTH: { x: 220, y: 15, w: 200, h: 140, label: 'ROI-1 [NORTH]' },
        SOUTH: { x: 220, y: 245, w: 200, h: 140, label: 'ROI-2 [SOUTH]' },
        WEST:  { x: 15, y: 140, w: 190, h: 120, label: 'ROI-3 [WEST]' },
        EAST:  { x: 435, y: 140, w: 190, h: 120, label: 'ROI-4 [EAST]' }
      };
    }

    async enableWebcam() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 400, facingMode: 'user' },
          audio: false
        });
        this.stream = stream;
        this.video.srcObject = stream;
        await this.video.play();
        this.mode = 'WEBCAM';
        return true;
      } catch (err) {
        console.warn('Webcam permission not granted or camera unavailable:', err);
        return false;
      }
    }

    disableWebcam() {
      if (this.stream) {
        this.stream.getTracks().forEach(track => track.stop());
        this.stream = null;
      }
      this.mode = 'CCTV';
    }

    render(simulation) {
      this.frameCount++;
      const w = this.canvas.width;
      const h = this.canvas.height;

      if (this.mode === 'WEBCAM' && this.video.readyState >= 2) {
        // Draw webcam feed
        this.ctx.save();
        this.ctx.translate(w, 0);
        this.ctx.scale(-1, 1); // mirror selfie camera
        this.ctx.drawImage(this.video, 0, 0, w, h);
        this.ctx.restore();

        // Process motion & presence detection over the 4 ROIs
        this.processWebcamMotion(simulation);
      } else {
        // Render synthetic overhead surveillance CCTV
        this.renderSyntheticCCTV(simulation);
      }

      // Draw ROI Boundary Overlays
      this.drawROIBoundaries();
    }

    processWebcamMotion(simulation) {
      const w = this.canvas.width;
      const h = this.canvas.height;
      const imgData = this.ctx.getImageData(0, 0, w, h);
      const data = imgData.data;

      let detectedInQuadrant = { NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0 };

      // Sample pixels across ROIs to compute motion difference
      if (this.lastFrameData && this.frameCount % 2 === 0) {
        const last = this.lastFrameData.data;
        for (const [key, roi] of Object.entries(this.rois)) {
          let motionPixels = 0;
          const step = 8; // sample every 8th pixel for 60fps performance
          for (let y = roi.y; y < roi.y + roi.h; y += step) {
            for (let x = roi.x; x < roi.x + roi.w; x += step) {
              const idx = (y * w + x) * 4;
              const diff = Math.abs(data[idx] - last[idx]) +
                           Math.abs(data[idx+1] - last[idx+1]) +
                           Math.abs(data[idx+2] - last[idx+2]);
              if (diff > 80) motionPixels++;
            }
          }
          if (motionPixels > 18) {
            detectedInQuadrant[key] = Math.min(6, Math.floor(motionPixels / 8));
          }
        }
      }
      this.lastFrameData = imgData;

      // Update vision metrics
      const totalDetected = Object.values(detectedInQuadrant).reduce((a, b) => a + b, 0);
      document.getElementById('cv-total-detected').textContent = `${totalDetected} Detected`;
      document.getElementById('cv-confidence').textContent = totalDetected > 0 ? '97.2%' : '88.4%';
      document.getElementById('cv-emergency-flag').textContent = 'READY';
    }

    renderSyntheticCCTV(simulation) {
      const ctx = this.ctx;
      const w = this.canvas.width;
      const h = this.canvas.height;

      // Background asphalt
      ctx.fillStyle = '#161c2b';
      ctx.fillRect(0, 0, w, h);

      // Roads
      ctx.fillStyle = '#222c42';
      // Vertical road
      ctx.fillRect(220, 0, 200, h);
      // Horizontal road
      ctx.fillRect(0, 130, w, 140);

      // Road markings (yellow dashed lines)
      ctx.strokeStyle = '#eab308';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 8]);
      // Vertical center
      ctx.beginPath();
      ctx.moveTo(320, 0); ctx.lineTo(320, 130);
      ctx.moveTo(320, 270); ctx.lineTo(320, h);
      ctx.stroke();
      // Horizontal center
      ctx.beginPath();
      ctx.moveTo(0, 200); ctx.lineTo(220, 200);
      ctx.moveTo(420, 200); ctx.lineTo(w, 200);
      ctx.stroke();
      ctx.setLineDash([]);

      // Move & draw synthetic CCTV vehicles
      let totalVeh = 0;
      for (const v of this.cctvVehicles) {
        v.x += v.dx;
        v.y += v.dy;
        totalVeh++;

        // Wrap around loop
        if (v.dy > 0 && v.y > 130) v.y = 20;
        if (v.dy < 0 && v.y < 270) v.y = 360;
        if (v.dx > 0 && v.x > 220) v.x = 20;
        if (v.dx < 0 && v.x < 420) v.x = 600;

        // Vehicle body
        ctx.fillStyle = v.color;
        ctx.fillRect(v.x - v.w/2, v.y - v.h/2, v.w, v.h);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.strokeRect(v.x - v.w/2, v.y - v.h/2, v.w, v.h);

        // Computer Vision AI Bounding Box & Detection Tag
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2;
        ctx.strokeRect(v.x - v.w/2 - 4, v.y - v.h/2 - 4, v.w + 8, v.h + 8);

        ctx.fillStyle = '#10b981';
        ctx.font = '10px "JetBrains Mono"';
        ctx.fillText(`${v.type} [96%]`, v.x - v.w/2 - 4, v.y - v.h/2 - 8);
      }

      // CCTV scanline effect
      ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
      for (let y = 0; y < h; y += 4) {
        ctx.fillRect(0, y, w, 1);
      }

      // CCTV Timestamp HUD
      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0').slice(0, 2);
      ctx.fillStyle = '#10b981';
      ctx.font = '12px "JetBrains Mono"';
      ctx.fillText(`CAM-01 [OVERHEAD SURVEILLANCE] ${timeStr} 30.0 FPS`, 16, 24);

      document.getElementById('cv-total-detected').textContent = `${totalVeh} Vehicles`;
    }

    drawROIBoundaries() {
      const ctx = this.ctx;
      for (const [key, roi] of Object.entries(this.rois)) {
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.7)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
        ctx.setLineDash([]);

        // Label banner
        ctx.fillStyle = 'rgba(14, 21, 38, 0.85)';
        ctx.fillRect(roi.x, roi.y, 110, 18);
        ctx.fillStyle = '#00f2fe';
        ctx.font = '10px "JetBrains Mono"';
        ctx.fillText(roi.label, roi.x + 6, roi.y + 13);
      }
    }
  }

  // =========================================================================
  // 6. 2D INTERSECTION RENDERER (CANVAS 700x700)
  // =========================================================================
  class IntersectionRenderer {
    constructor(canvas, simulation, controller) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.sim = simulation;
      this.ctrl = controller;
      this.flashTick = 0;
    }

    render() {
      this.flashTick++;
      const ctx = this.ctx;
      const w = this.canvas.width;
      const h = this.canvas.height;
      const c = w / 2; // Center (350)
      const rw = this.sim.roadWidth; // 140
      const hw = rw / 2; // 70

      // Ground / grass
      ctx.fillStyle = '#090e1a';
      ctx.fillRect(0, 0, w, h);

      // Roads
      ctx.fillStyle = '#182133';
      // Vertical road
      ctx.fillRect(c - hw, 0, rw, h);
      // Horizontal road
      ctx.fillRect(0, c - hw, w, rw);

      // Intersection junction box
      ctx.fillStyle = '#202b40';
      ctx.fillRect(c - hw, c - hw, rw, rw);

      // Yellow Centerlines
      ctx.strokeStyle = '#eab308';
      ctx.lineWidth = 3;
      ctx.beginPath();
      // North
      ctx.moveTo(c, 0); ctx.lineTo(c, c - hw - 20);
      // South
      ctx.moveTo(c, c + hw + 20); ctx.lineTo(c, h);
      // West
      ctx.moveTo(0, c); ctx.lineTo(c - hw - 20, c);
      // East
      ctx.moveTo(c + hw + 20, c); ctx.lineTo(w, c);
      ctx.stroke();

      // Zebra Crosswalk Stripes & Stop lines
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 4;
      // North Stopline
      ctx.beginPath(); ctx.moveTo(c - hw, c - hw - 15); ctx.lineTo(c, c - hw - 15); ctx.stroke();
      // South Stopline
      ctx.beginPath(); ctx.moveTo(c, c + hw + 15); ctx.lineTo(c + hw, c + hw + 15); ctx.stroke();
      // West Stopline
      ctx.beginPath(); ctx.moveTo(c - hw - 15, c); ctx.lineTo(c - hw - 15, c + hw); ctx.stroke();
      // East Stopline
      ctx.beginPath(); ctx.moveTo(c + hw + 15, c - hw); ctx.lineTo(c + hw + 15, c); ctx.stroke();

      // Draw Crosswalk Zebra Stripes
      this.drawCrosswalk(c - hw, c - hw - 12, rw, 12, 'h');
      this.drawCrosswalk(c - hw, c + hw, rw, 12, 'h');
      this.drawCrosswalk(c - hw - 12, c - hw, 12, rw, 'v');
      this.drawCrosswalk(c + hw, c - hw, 12, rw, 'v');

      // Draw Protected Turn Guidance Dashed Arcs
      this.drawTurnGuidance(c, hw);

      // Draw Painted Lane Arrows (Left, Straight, Right)
      this.drawLaneTurnArrows(c, hw);

      // Draw Vehicles with Turning Kinematics & Amber Blinkers
      this.drawVehicles(c, hw);

      // Draw 3-Aspect Traffic Signal Heads with Glowing Lamps
      this.drawSignalPoles(c, hw);

      // Draw Rain if active
      if (this.sim.isRaining) {
        ctx.strokeStyle = 'rgba(180, 220, 255, 0.4)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (const drop of this.sim.rainDrops) {
          ctx.moveTo(drop.x, drop.y);
          ctx.lineTo(drop.x - 2, drop.y + drop.len);
        }
        ctx.stroke();
      }
    }

    drawCrosswalk(x, y, w, h, dir) {
      const ctx = this.ctx;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
      if (dir === 'h') {
        const stripes = 8;
        const step = w / stripes;
        for (let i = 0; i < stripes; i += 2) {
          ctx.fillRect(x + i * step, y, step, h);
        }
      } else {
        const stripes = 8;
        const step = h / stripes;
        for (let i = 0; i < stripes; i += 2) {
          ctx.fillRect(x, y + i * step, w, step);
        }
      }
    }

    drawTurnGuidance(c, hw) {
      const ctx = this.ctx;
      ctx.strokeStyle = 'rgba(0, 242, 254, 0.18)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 6]);

      // Right turn guide North to West: arc centered at (c-hw, c-hw), radius 35
      ctx.beginPath();
      ctx.arc(c - hw, c - hw, 35, 0, Math.PI / 2);
      ctx.stroke();

      // Left turn guide North to East: arc centered at (c+hw, c-hw), radius 105
      ctx.beginPath();
      ctx.arc(c + hw, c - hw, 105, Math.PI / 2, Math.PI);
      ctx.stroke();

      // Right turn guide South to East: arc centered at (c+hw, c+hw), radius 35
      ctx.beginPath();
      ctx.arc(c + hw, c + hw, 35, Math.PI, Math.PI * 1.5);
      ctx.stroke();

      // Left turn guide South to West: arc centered at (c-hw, c+hw), radius 105
      ctx.beginPath();
      ctx.arc(c - hw, c + hw, 105, -Math.PI / 2, 0);
      ctx.stroke();

      ctx.setLineDash([]);
    }

    drawLaneTurnArrows(c, hw) {
      const ctx = this.ctx;
      ctx.fillStyle = '#64748b';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      // North approach painted lane arrows
      ctx.fillText('↰ ↑ ↱', c - hw / 2, c - hw - 35);
      // South approach painted lane arrows
      ctx.fillText('↰ ↑ ↱', c + hw / 2, c + hw + 35);

      ctx.save();
      // West approach
      ctx.translate(c - hw - 35, c + hw / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText('↰ ↑ ↱', 0, 0);
      ctx.restore();

      ctx.save();
      // East approach
      ctx.translate(c + hw + 35, c - hw / 2);
      ctx.rotate(Math.PI / 2);
      ctx.fillText('↰ ↑ ↱', 0, 0);
      ctx.restore();
    }

    getTrajectory(direction, turnIntent, pos, c, hw) {
      // Parametric trajectory calculation for smooth turning
      let rx = -hw / 2; // -35
      let ry = pos - c;
      let rHeading = Math.PI / 2; // South

      if (turnIntent === 'straight') {
        rx = -hw / 2;
        ry = pos - c;
        rHeading = Math.PI / 2;
      } else if (turnIntent === 'right') {
        if (pos <= 280) {
          rx = -35;
          ry = pos - c;
          rHeading = Math.PI / 2;
        } else if (pos < 350) {
          const t = (pos - 280) / 70;
          rx = -70 + 35 * Math.cos(t * Math.PI / 2);
          ry = -70 + 35 * Math.sin(t * Math.PI / 2);
          rHeading = Math.PI / 2 + t * (Math.PI / 2);
        } else {
          rx = -70 - (pos - 350);
          ry = -35;
          rHeading = Math.PI;
        }
      } else if (turnIntent === 'left') {
        if (pos <= 280) {
          rx = -35;
          ry = pos - c;
          rHeading = Math.PI / 2;
        } else if (pos < 420) {
          const t = (pos - 280) / 140;
          rx = 70 - 105 * Math.cos(t * Math.PI / 2);
          ry = -70 + 105 * Math.sin(t * Math.PI / 2);
          rHeading = Math.PI / 2 - t * (Math.PI / 2);
        } else {
          rx = 70 + (pos - 420);
          ry = 35;
          rHeading = 0;
        }
      }

      let vx = 0, vy = 0, angle = 0;
      if (direction === Direction.NORTH) {
        vx = c + rx;
        vy = c + ry;
        angle = rHeading;
      } else if (direction === Direction.EAST) {
        vx = c - ry;
        vy = c + rx;
        angle = rHeading + Math.PI / 2;
      } else if (direction === Direction.SOUTH) {
        vx = c - rx;
        vy = c - ry;
        angle = rHeading + Math.PI;
      } else if (direction === Direction.WEST) {
        vx = c + ry;
        vy = c - rx;
        angle = rHeading - Math.PI / 2;
      }

      return { x: vx, y: vy, angle: angle };
    }

    drawVehicles(c, hw) {
      const ctx = this.ctx;

      for (const [d, lane] of Object.entries(this.sim.vehicles)) {
        for (const v of lane) {
          const coords = this.getTrajectory(d, v.turnIntent, v.pos, c, hw);
          const vx = coords.x;
          const vy = coords.y;
          const angle = coords.angle;

          ctx.save();
          ctx.translate(vx, vy);
          ctx.rotate(angle);

          // Vehicle Body Shadow
          ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
          ctx.fillRect(-v.type.length/2 + 2, -v.type.width/2 + 2, v.type.length, v.type.width);

          // Vehicle Body
          ctx.fillStyle = v.type.color;
          ctx.beginPath();
          ctx.roundRect(-v.type.length/2, -v.type.width/2, v.type.length, v.type.width, 3);
          ctx.fill();

          // Windshield & Roof Detail
          ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
          ctx.fillRect(-v.type.length/4, -v.type.width/2 + 2, v.type.length/2, v.type.width - 4);

          // Turn Direction Symbol on roof (↰ Left, ↱ Right, ↑ Straight)
          ctx.fillStyle = '#ffffff';
          ctx.font = '8px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const sym = v.turnIntent === 'left' ? '↰' : (v.turnIntent === 'right' ? '↱' : '↑');
          ctx.fillText(sym, 0, 0);

          // Headlights
          ctx.fillStyle = '#fef08a';
          ctx.fillRect(v.type.length/2 - 2, -v.type.width/2 + 1, 2, 3);
          ctx.fillRect(v.type.length/2 - 2, v.type.width/2 - 4, 2, 3);

          // Brake lights (glow red when stopping)
          if (v.isStopped || v.speed < 0.5) {
            ctx.fillStyle = '#ef4444';
            ctx.shadowColor = '#ef4444';
            ctx.shadowBlur = 6;
            ctx.fillRect(-v.type.length/2, -v.type.width/2 + 1, 2, 3);
            ctx.fillRect(-v.type.length/2, v.type.width/2 - 4, 2, 3);
            ctx.shadowBlur = 0;
          }

          // Flashing Amber Turn Indicator Blinkers
          const isBlinkOn = Math.floor(this.flashTick / 6) % 2 === 0;
          if (isBlinkOn && v.turnIntent !== 'straight' && v.pos < 440) {
            ctx.fillStyle = '#f59e0b';
            ctx.shadowColor = '#f59e0b';
            ctx.shadowBlur = 8;
            if (v.turnIntent === 'left') {
              // Left side amber blinkers
              ctx.fillRect(v.type.length/2 - 2, -v.type.width/2, 3, 2);
              ctx.fillRect(-v.type.length/2, -v.type.width/2, 3, 2);
            } else if (v.turnIntent === 'right') {
              // Right side amber blinkers
              ctx.fillRect(v.type.length/2 - 2, v.type.width/2 - 2, 3, 2);
              ctx.fillRect(-v.type.length/2, v.type.width/2 - 2, 3, 2);
            }
            ctx.shadowBlur = 0;
          }

          // Ambulance Flashing Siren Lights
          if (v.isEmergency) {
            const isRed = Math.floor(this.flashTick / 4) % 2 === 0;
            ctx.fillStyle = isRed ? '#ef4444' : '#38bdf8';
            ctx.shadowColor = isRed ? '#ef4444' : '#38bdf8';
            ctx.shadowBlur = 14;
            ctx.beginPath();
            ctx.arc(0, 0, 5, 0, Math.PI * 2);
            ctx.fill();
            ctx.shadowBlur = 0;
          }

          ctx.restore();
        }
      }
    }

    drawSignalPoles(c, hw) {
      // 4 Signal head locations on the intersection corners
      const poles = [
        { dir: Direction.NORTH, x: c - hw - 36, y: c - hw - 75 },
        { dir: Direction.SOUTH, x: c + hw + 12, y: c + hw + 15 },
        { dir: Direction.WEST,  x: c - hw - 75, y: c + hw + 12 },
        { dir: Direction.EAST,  x: c + hw + 15, y: c - hw - 36 }
      ];

      for (const p of poles) {
        this.drawSingleSignalHead(p.x, p.y, this.ctrl.lights[p.dir]);
      }
    }

    drawSingleSignalHead(x, y, state) {
      const ctx = this.ctx;
      const bw = 24, bh = 58;

      // Housing box
      ctx.fillStyle = '#0f172a';
      ctx.strokeStyle = '#334155';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(x, y, bw, bh, 6);
      ctx.fill();
      ctx.stroke();

      const cx = x + bw / 2;
      const r = 7;

      // Red Lamp
      const isRed = state === LightState.RED;
      ctx.fillStyle = isRed ? '#ef4444' : '#3b1818';
      if (isRed) {
        ctx.shadowColor = '#ef4444';
        ctx.shadowBlur = 12;
      }
      ctx.beginPath();
      ctx.arc(cx, y + 12, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      // Amber / Yellow Lamp
      const isYellow = state === LightState.YELLOW;
      ctx.fillStyle = isYellow ? '#f59e0b' : '#3d2c0e';
      if (isYellow) {
        ctx.shadowColor = '#f59e0b';
        ctx.shadowBlur = 12;
      }
      ctx.beginPath();
      ctx.arc(cx, y + 29, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      // Green Lamp
      const isGreen = state === LightState.GREEN;
      ctx.fillStyle = isGreen ? '#10b981' : '#0e3321';
      if (isGreen) {
        ctx.shadowColor = '#10b981';
        ctx.shadowBlur = 12;
      }
      ctx.beginPath();
      ctx.arc(cx, y + 46, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  // =========================================================================
  // 7. REAL-TIME TELEMETRY CHART (CANVAS)
  // =========================================================================
  class TelemetryChart {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.aiData = [];
      this.fixedBaseline = 21.0;
      this.maxPoints = 40;
    }

    addDataPoint(aiVal) {
      this.aiData.push(aiVal);
      if (this.aiData.length > this.maxPoints) {
        this.aiData.shift();
      }
      this.render();
    }

    render() {
      const ctx = this.ctx;
      const w = this.canvas.width;
      const h = this.canvas.height;
      const pad = 24;

      ctx.clearRect(0, 0, w, h);

      // Chart background grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
      ctx.lineWidth = 1;
      for (let y = pad; y < h - pad; y += 35) {
        ctx.beginPath();
        ctx.moveTo(pad, y); ctx.lineTo(w - pad, y);
        ctx.stroke();
      }

      const maxY = 35;
      const graphW = w - pad * 2;
      const graphH = h - pad * 2;

      // 1. Draw Fixed Timer Baseline (Amber dashed line)
      const fixedY = h - pad - (this.fixedBaseline / maxY) * graphH;
      ctx.strokeStyle = 'rgba(245, 158, 11, 0.85)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 6]);
      ctx.beginPath();
      ctx.moveTo(pad, fixedY);
      ctx.lineTo(w - pad, fixedY);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = '#f59e0b';
      ctx.font = '10px "JetBrains Mono"';
      ctx.fillText(`Fixed: ${this.fixedBaseline}s`, w - pad - 65, fixedY - 6);

      // 2. Draw AI Adaptive Curve (Cyan glowing curve)
      if (this.aiData.length < 2) return;

      const stepX = graphW / (this.maxPoints - 1);
      ctx.strokeStyle = '#00f2fe';
      ctx.lineWidth = 2.5;
      ctx.shadowColor = '#00f2fe';
      ctx.shadowBlur = 8;
      ctx.beginPath();

      for (let i = 0; i < this.aiData.length; i++) {
        const px = pad + i * stepX;
        const py = h - pad - (Math.min(maxY, this.aiData[i]) / maxY) * graphH;
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Current AI value marker
      const lastX = pad + (this.aiData.length - 1) * stepX;
      const lastVal = this.aiData[this.aiData.length - 1];
      const lastY = h - pad - (Math.min(maxY, lastVal) / maxY) * graphH;

      ctx.fillStyle = '#00f2fe';
      ctx.beginPath();
      ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // =========================================================================
  // 8. MASTER APPLICATION CONTROLLER
  // =========================================================================
  class TrafficAppMaster {
    constructor() {
      this.audio = new SoundFX();
      this.controller = new AITrafficController();
      this.simulation = new TrafficSimulation(this.controller);

      // Canvases
      this.simCanvas = document.getElementById('simCanvas');
      this.cvCanvas = document.getElementById('cvCanvas');
      this.chartCanvas = document.getElementById('telemetryChart');
      this.videoElem = document.getElementById('webcam-video');

      this.renderer = new IntersectionRenderer(this.simCanvas, this.simulation, this.controller);
      this.visionSensor = new VisionPerceptionSensor(this.cvCanvas, this.videoElem);
      this.chart = new TelemetryChart(this.chartCanvas);

      this.simSpeed = 1.0;
      this.lastTimestamp = performance.now();
      this.telemetryTimer = 0;

      this.initEventListeners();
      this.populateRankingTable();
      this.addLogEntry('Neura-Traffic AI 4.0 Laptop Model Initialized.');
      this.addLogEntry('Controller State: Dynamic Queue Optimization Active.');

      // Start Simulation Loop
      requestAnimationFrame(this.mainLoop.bind(this));
    }

    initEventListeners() {
      // Audio toggle
      document.getElementById('btn-audio-toggle').addEventListener('click', (e) => {
        this.audio.enabled = !this.audio.enabled;
        e.currentTarget.querySelector('.icon').textContent = this.audio.enabled ? '🔊' : '🔇';
      });

      // Day / Night mode
      document.getElementById('btn-night-toggle').addEventListener('click', (e) => {
        document.body.classList.toggle('day-mode');
        const isDay = document.body.classList.contains('day-mode');
        e.currentTarget.querySelector('.icon').textContent = isDay ? '☀️' : '🌙';
      });

      // Presentation Modal
      const modal = document.getElementById('presentation-modal');
      document.getElementById('btn-presentation-mode').addEventListener('click', () => {
        modal.style.display = 'flex';
      });
      document.getElementById('btn-close-modal').addEventListener('click', () => {
        modal.style.display = 'none';
      });
      document.getElementById('btn-close-modal-footer').addEventListener('click', () => {
        modal.style.display = 'none';
      });

      // Fullscreen
      document.getElementById('btn-fullscreen').addEventListener('click', () => {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen().catch(() => {});
        } else {
          document.exitFullscreen();
        }
      });

      // Control Mode Toggles
      const btnAI = document.getElementById('mode-ai');
      const btnFixed = document.getElementById('mode-fixed');
      btnAI.addEventListener('click', () => {
        btnAI.classList.add('active');
        btnFixed.classList.remove('active');
        this.controller.setMode('AI_DYNAMIC');
        document.getElementById('status-engine').textContent = 'ONLINE (OPTIMIZING)';
        document.getElementById('status-engine').className = 'status-val text-green';
      });
      btnFixed.addEventListener('click', () => {
        btnFixed.classList.add('active');
        btnAI.classList.remove('active');
        this.controller.setMode('FIXED');
        document.getElementById('status-engine').textContent = 'STATIC (25s CYCLE)';
        document.getElementById('status-engine').className = 'status-val text-yellow';
      });

      // Deck Tabs
      const tabBtns = document.querySelectorAll('.tab-btn');
      tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          tabBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const target = btn.dataset.tab;
          document.querySelectorAll('.tab-content').forEach(tc => {
            tc.classList.toggle('active', tc.id === target);
          });
        });
      });

      // Camera switch actions
      const btnWebcam = document.getElementById('btn-use-webcam');
      const btnCCTV = document.getElementById('btn-use-cctv');
      const webcamHelp = document.getElementById('webcam-instructions');

      btnWebcam.addEventListener('click', async () => {
        const ok = await this.visionSensor.enableWebcam();
        if (ok) {
          btnWebcam.classList.add('active');
          btnCCTV.classList.remove('active');
          webcamHelp.style.display = 'block';
          document.getElementById('status-camera').textContent = 'INTEGRATED WEBCAM';
          document.getElementById('feed-status-badge').textContent = 'LAPTOP WEBCAM 30 FPS';
          this.addLogEntry('📷 Activated Laptop Webcam Sensor Input Mode.');
        } else {
          alert('Could not access laptop webcam. Please ensure camera permissions are allowed in your browser.');
        }
      });

      btnCCTV.addEventListener('click', () => {
        this.visionSensor.disableWebcam();
        btnCCTV.classList.add('active');
        btnWebcam.classList.remove('active');
        webcamHelp.style.display = 'none';
        document.getElementById('status-camera').textContent = 'SYNTHETIC CCTV';
        document.getElementById('feed-status-badge').textContent = 'CAM-01 [OVERHEAD CCTV] 30 FPS';
        this.addLogEntry('🛰️ Switched to Synthetic CCTV Overhead Stream.');
      });

      // Speed multipliers
      document.querySelectorAll('.btn-speed').forEach(btn => {
        btn.addEventListener('click', (e) => {
          document.querySelectorAll('.btn-speed').forEach(b => b.classList.remove('active'));
          e.target.classList.add('active');
          this.simSpeed = parseFloat(e.target.dataset.speed);
          document.getElementById('status-speed').textContent = `${this.simSpeed.toFixed(1)}x`;
        });
      });

      // Spawn rate slider
      const slider = document.getElementById('spawnRateSlider');
      slider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        this.simulation.spawnRate = val;
        const label = val <= 1.0 ? 'Heavy Congestion' : (val <= 2.0 ? 'Moderate Traffic' : 'Light Traffic');
        document.getElementById('spawnRateVal').textContent = `${label} (${val.toFixed(1)}s)`;
      });

      // Rain toggle
      document.getElementById('btn-weather-toggle').addEventListener('click', (e) => {
        this.simulation.isRaining = !this.simulation.isRaining;
        e.currentTarget.classList.toggle('active', this.simulation.isRaining);
        this.addLogEntry(this.simulation.isRaining ? '🌧️ Rain Simulation Enabled.' : '☀️ Rain Stopped. Weather Clear.');
      });

      // Reset Simulation
      document.getElementById('btn-reset-sim').addEventListener('click', () => {
        for (const d of Object.values(Direction)) {
          this.simulation.vehicles[d] = [];
        }
        this.controller.stats.vehiclesCleared = 0;
        this.controller.stats.totalWaitAccumulator = 0;
        this.controller.stats.completedVehicleCount = 0;
        this.controller.stats.emergencyPreemptions = 0;
        this.chart.aiData = [];
        this.addLogEntry('🔄 Simulation & Telemetry Metrics Reset.');
      });

      // Clear Log
      document.getElementById('btn-clear-log').addEventListener('click', () => {
        document.getElementById('decision-log-box').innerHTML = '';
      });
    }

    spawnEmergency(direction) {
      this.simulation.spawnEmergency(direction);
    }

    injectBurst(corridor) {
      this.simulation.injectBurst(corridor);
    }

    showEmergencyBanner(direction) {
      const banner = document.getElementById('emergency-banner');
      document.getElementById('emergency-text').textContent =
        `Ambulance detected on ${direction.toUpperCase()} corridor • Instant green corridor activated`;
      banner.style.display = 'flex';
    }

    hideEmergencyBanner() {
      document.getElementById('emergency-banner').style.display = 'none';
    }

    showCutoffPill() {
      const pill = document.getElementById('cutoff-pill');
      pill.style.display = 'block';
      setTimeout(() => {
        pill.style.display = 'none';
      }, 2500);
    }

    addLogEntry(msg) {
      const box = document.getElementById('decision-log-box');
      if (!box) return;
      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0];

      let tagClass = 'log-tag-ai';
      let tagText = '[AI]';
      if (msg.includes('EMERGENCY') || msg.includes('Ambulance')) {
        tagClass = 'log-tag-emerg';
        tagText = '[EMERG]';
      } else if (msg.includes('Early Cutoff') || msg.includes('Switched')) {
        tagClass = 'log-tag-warn';
        tagText = '[STATE]';
      }

      const div = document.createElement('div');
      div.className = 'log-entry';
      div.innerHTML = `<span class="log-time">${timeStr}</span> <span class="${tagClass}">${tagText}</span> ${msg}`;
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }

    populateRankingTable() {
      const tbody = document.getElementById('ranking-table-body');
      if (!tbody) return;

      const approaches = [
        { name: 'North Approach', dir: Direction.NORTH },
        { name: 'East Approach', dir: Direction.EAST },
        { name: 'South Approach', dir: Direction.SOUTH },
        { name: 'West Approach', dir: Direction.WEST }
      ];

      let html = '';
      for (const a of approaches) {
        const metrics = this.simulation.getApproachMetrics(a.dir);
        const score = (metrics.queueCount * 2.0) + (metrics.transitWeight * 2.5) + (metrics.maxWaitTime * 0.6) + (metrics.hasEmergency ? 250 : 0);
        const isActive = this.controller.activeDirection === a.dir;
        const isGreen = isActive && this.controller.phaseType === 'GREEN';
        const isYellow = isActive && this.controller.phaseType === 'YELLOW';

        let badgeStyle = 'background: rgba(255, 255, 255, 0.05); color: #94a3b8';
        let badgeText = 'WAITING (RED)';
        if (isGreen) {
          badgeStyle = 'background: rgba(16, 185, 129, 0.2); color: #10b981; font-weight: bold';
          badgeText = 'EXCLUSIVE GREEN (TURNS ACTIVE)';
        } else if (isYellow) {
          badgeStyle = 'background: rgba(245, 158, 11, 0.2); color: #f59e0b; font-weight: bold';
          badgeText = 'YELLOW CLEARANCE';
        }

        html += `
          <tr>
            <td><strong>${a.name}</strong></td>
            <td>${metrics.queueCount} veh</td>
            <td>${metrics.maxWaitTime.toFixed(1)}s</td>
            <td>${metrics.transitWeight > 0 ? 'Buses/Trucks' : (metrics.hasEmergency ? 'Ambulance 🚨' : 'Standard')}</td>
            <td><strong class="text-cyan">${score.toFixed(1)} pts</strong></td>
            <td><span class="chip-formula" style="${badgeStyle}">${badgeText}</span></td>
          </tr>
        `;
      }
      tbody.innerHTML = html;
    }

    updateUI() {
      // Top Status Bar Countdown
      const rem = Math.max(0, this.controller.phaseTimer);
      document.getElementById('ai-timer-val').textContent = `${rem.toFixed(1)}s`;
      document.getElementById('ai-active-phase').textContent =
        `${this.controller.activeDirection.toUpperCase()} ${this.controller.phaseType} (PROTECTED TURNS)`;

      // Progress Ring calculation
      const ring = document.getElementById('ring-progress');
      if (ring) {
        const circumference = 2 * Math.PI * 42; // r=42 -> ~263.89
        const fraction = Math.min(1.0, rem / Math.max(1, this.controller.allocatedGreen));
        const offset = circumference * (1 - fraction);
        ring.style.strokeDashoffset = offset;
        ring.style.stroke = this.controller.isGreenPhase() ? 'var(--neon-green)' : 'var(--neon-amber)';
      }

      // Corridor Card Updates
      for (const d of Object.values(Direction)) {
        const lower = d.toLowerCase();
        const state = this.controller.lights[d];
        const ind = document.getElementById(`ind-${lower}`);
        const card = document.getElementById(`corridor-${lower}`);
        const cntElem = document.getElementById(`cnt-${lower}`);
        const waitElem = document.getElementById(`wait-${lower}`);
        const barElem = document.getElementById(`bar-${lower}`);

        if (ind) {
          ind.textContent = state;
          ind.className = `light-indicator ${state === LightState.GREEN ? 'green' : (state === LightState.YELLOW ? 'yellow' : '')}`;
        }
        if (card) {
          card.className = `corridor-card ${state === LightState.GREEN ? 'active-green' : (state === LightState.YELLOW ? 'active-amber' : '')}`;
        }

        const laneVehicles = this.simulation.vehicles[d];
        const queued = laneVehicles.filter(v => v.pos <= this.simulation.stopLineDist + 15).length;
        const maxWait = laneVehicles.reduce((acc, v) => Math.max(acc, v.waitTime), 0);

        if (cntElem) cntElem.textContent = queued;
        if (waitElem) waitElem.textContent = `${maxWait.toFixed(1)}s`;
        if (barElem) barElem.style.width = `${Math.min(100, queued * 18)}%`;
      }

      // Telemetry Metrics
      const avgWait = this.controller.getAvgWaitTime();
      document.getElementById('metric-avg-wait').textContent = `${avgWait.toFixed(1)}s`;
      document.getElementById('metric-cleared').textContent = this.controller.stats.vehiclesCleared;
      document.getElementById('metric-preemptions').textContent = this.controller.stats.emergencyPreemptions;

      // Fuel & CO2 savings calculation (0.45g CO2/sec idling vehicle saved)
      const baselineTotalWait = this.controller.stats.completedVehicleCount * 21.0;
      const actualTotalWait = this.controller.stats.totalWaitAccumulator;
      const secondsSaved = Math.max(0, baselineTotalWait - actualTotalWait);
      const co2Kg = (secondsSaved * 0.00045).toFixed(2);
      document.getElementById('metric-co2').textContent = `${co2Kg} kg`;

      if (baselineTotalWait > 0 && actualTotalWait > 0) {
        const reduction = Math.max(0, ((baselineTotalWait - actualTotalWait) / baselineTotalWait) * 100);
        document.getElementById('tag-wait-diff').textContent = `-${reduction.toFixed(1)}% vs Fixed`;
      }
    }

    mainLoop(now) {
      const dtRaw = (now - this.lastTimestamp) / 1000;
      this.lastTimestamp = now;
      const dt = Math.min(0.1, dtRaw) * this.simSpeed;

      // Update Controller & Physics
      this.controller.update(dt, this.simulation);
      this.simulation.update(dt);

      // Render 2D Intersection
      this.renderer.render();

      // Render Camera / Vision
      this.visionSensor.render(this.simulation);

      // Update UI & Telemetry
      this.telemetryTimer += dt;
      if (this.telemetryTimer >= 0.8) {
        this.telemetryTimer = 0;
        this.updateUI();
        this.populateRankingTable();
        const currentWait = this.controller.getAvgWaitTime();
        this.chart.addDataPoint(currentWait > 0 ? currentWait : 6.0);
      }

      requestAnimationFrame(this.mainLoop.bind(this));
    }
  }

  // Expose global entry point
  window.addEventListener('DOMContentLoaded', () => {
    window.TrafficApp = new TrafficAppMaster();
  });
})();
