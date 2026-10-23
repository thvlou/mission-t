// Match the highway drivetrain's brake/reverse threshold; coasting is not braking.
export function vehicleLightState(throttle = 0, forwardSpeed = 0, handbrake = false) {
  return {
    brake: !!handbrake || (throttle < 0 && forwardSpeed > 0.5),
    reverse: throttle < 0 && forwardSpeed <= 0.5,
  };
}

// Side-view stunt controls reverse the motor relative to the current track side.
export function stuntLightState(sim) {
  const throttle = sim.input?.throttle || 0;
  const forwardSpeed = (sim.v || 0) * (sim.side || 1);
  return vehicleLightState(throttle, forwardSpeed, false);
}
