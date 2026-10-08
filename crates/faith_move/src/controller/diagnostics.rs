//! Read-only entry checks for a host's parkour inspector. These describe the current
//! position and input, not a prediction: fixtures and earlier moves may take priority.
//! Keep numerical gates aligned with `ground`, `air`, `air_transitions`, and `land`.

use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CheckStatus {
    Blocked,
    Ready,
    Active,
}

#[derive(Debug)]
pub struct MoveCheck {
    pub name: &'static str,
    pub status: CheckStatus,
    /// First unmet requirement, or the input that activates an eligible move.
    pub reason: String,
}

#[derive(Debug)]
pub struct Diagnostics {
    pub checks: [MoveCheck; 6],
    pub fall_height: f32,
    pub jump_buffer: f32,
    pub roll_window: f32,
    pub dodging: bool,
    pub springboard_approach: bool,
}

fn require(condition: bool, reason: impl Into<String>) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(reason.into())
    }
}

fn check(
    name: &'static str,
    active: bool,
    evaluate: impl FnOnce() -> Result<String, String>,
) -> MoveCheck {
    let (status, reason) = if active {
        (CheckStatus::Active, "Move in progress".into())
    } else {
        match evaluate() {
            Ok(reason) => (CheckStatus::Ready, reason),
            Err(reason) => (CheckStatus::Blocked, reason),
        }
    };
    MoveCheck {
        name,
        status,
        reason,
    }
}

impl Controller {
    pub fn diagnostics(&self, input: &Input, world: &dyn World) -> Diagnostics {
        // Use the same door collision as step(), including before the first frame.
        let closed = world
            .fixtures()
            .iter()
            .enumerate()
            .filter_map(|(i, f)| match f {
                Fixture::Door { b, .. }
                    if self.doors_open.get(i).copied().unwrap_or(0.0) == 0.0 =>
                {
                    Some(*b)
                }
                _ => None,
            })
            .collect();
        let world = &WithDoors { world, closed };
        let tu = &self.tuning;
        let movement = input.move_axis.clamp_length_max(1.0);
        let fwd = self.forward();
        let forward_speed = self.vel.dot(fwd);
        let fall_height = (self.fall_peak - self.body_y()).max(0.0);
        let roll_window = (tu.roll_window - self.roll_trigger_age).max(0.0);
        let airborne = || {
            require(self.state == State::Air, "Jump or fall to enter this move")?;
            require(
                !self.dodging || self.vel.y < -tu.dodge_exit_fall_speed,
                "Dodge locks wall moves until descending",
            )
        };

        let jump = check("Jump", false, || {
            require(
                self.springboard.is_none(),
                "Committed to springboard run-in",
            )?;
            let coyote = self.state == State::Air
                && !self.jumped_since_ground
                && self.air_time < tu.coyote_time
                && !self.crouched
                && !self.coiled
                && !self.dodging;
            require(
                (self.state == State::Ground && self.grounded(world)) || coyote,
                "Need ground or an unused coyote window",
            )?;
            let stand = Body {
                half_width: tu.half_width,
                height: tu.stand_height,
            };
            require(
                !self.crouched || world.is_free(&stand.aabb(self.feet)),
                "Ceiling prevents standing up",
            )?;
            Ok(if coyote {
                "Press jump before coyote time expires"
            } else {
                "Press jump; full strafe selects dodge"
            }
            .into())
        });
        let slide = check("Slide", matches!(self.state, State::Slide { .. }), || {
            require(
                self.state == State::Ground && self.grounded(world),
                "Need ground contact",
            )?;
            require(!self.crouched, "Stand up before starting a slide")?;
            require(
                forward_speed >= tu.slide_min_speed,
                format!(
                    "Forward speed {forward_speed:.1} / {:.1} m/s",
                    tu.slide_min_speed
                ),
            )?;
            Ok("Tap crouch while moving forward".into())
        });
        let vault = check("Vault", matches!(self.state, State::Vault(_)), || {
            airborne()?;
            require(movement.y > 0.8, "Hold forward above 0.80")?;
            let view = fwd * self.pitch.cos() + Vec3::Y * self.pitch.sin();
            let plan = vault::plan(world, tu, self.body(), self.feet, self.vel, fwd, view)
                .ok_or("Need a reachable ledge and clear landing")?;
            Ok(format!("Hold forward: {}", plan.anim()))
        });
        let wallrun = check(
            "Wallrun",
            matches!(self.state, State::WallRun { .. }),
            || {
                airborne()?;
                require(
                    !self.crouched && !self.coiled,
                    "Release crouch / untuck your legs",
                )?;
                require(movement.y > 0.3, "Hold forward above 0.30")?;
                require(
                    self.horizontal_speed() >= tu.wallrun_min_speed,
                    format!(
                        "Speed {:.1} / {:.1} m/s",
                        self.horizontal_speed(),
                        tu.wallrun_min_speed
                    ),
                )?;
                require(forward_speed >= 0.0, "Move in the direction you face")?;
                require(
                    self.vel.y > -tu.wallrun_stop_fall_speed,
                    "Descending too fast to catch a wall",
                )?;
                let normalized = Input {
                    move_axis: movement,
                    ..*input
                };
                require(
                    self.find_wallrun(&normalized, world).is_some(),
                    "Need a tall wall at a shallow approach",
                )?;
                Ok("Valid wall contact; keep holding forward".into())
            },
        );
        let wallclimb = check(
            "Wallclimb",
            matches!(
                self.state,
                State::WallClimb { .. } | State::WallClimbTurned { .. }
            ),
            || {
                airborne()?;
                require(movement.y > 0.8, "Hold forward above 0.80")?;
                require(
                    !self.climbed_this_air,
                    "Already climbed this jump; land to reset",
                )?;
                require(!self.coiled, "Untuck your legs")?;
                require(
                    self.jumped_since_ground && self.vel.y > 0.0,
                    "Must still be rising from a jump",
                )?;
                require(forward_speed >= 0.0, "Move toward the wall")?;
                require(
                    self.find_wallclimb(world).is_some(),
                    format!(
                        "Face a nearby tall wall within {:.0} deg",
                        tu.wallclimb_max_angle_deg
                    ),
                )?;
                Ok("Valid wall contact; keep holding forward".into())
            },
        );
        let roll = check(
            "Landing roll",
            matches!(self.state, State::Roll { .. }),
            || {
                require(
                    self.state == State::Air && self.vel.y < 0.0,
                    "Must be falling",
                )?;
                require(
                    fall_height >= tu.roll_height,
                    format!("Fall {fall_height:.1} / {:.1} m", tu.roll_height),
                )?;
                require(
                    fall_height < tu.lethal_fall_height,
                    "Fall exceeds the lethal height",
                )?;
                require(
                    !self.turned_in_air && self.turn.is_none(),
                    "An air turn prevents a roll",
                )?;
                require(
                    !self.melee.is_some_and(|m| m.kind == MeleeKind::AirKick),
                    "Air kick prevents a roll",
                )?;
                if roll_window > 0.0 {
                    Ok(format!(
                        "Armed for {:.0} ms; land before it expires",
                        roll_window * 1000.0
                    ))
                } else if self.roll_trigger_age < tu.roll_retrigger {
                    Err(format!(
                        "Crouch retrigger in {:.0} ms",
                        (tu.roll_retrigger - self.roll_trigger_age) * 1000.0
                    ))
                } else {
                    Err(format!(
                        "Tap crouch within {:.0} ms of landing",
                        tu.roll_window * 1000.0
                    ))
                }
            },
        );
        Diagnostics {
            checks: [jump, slide, vault, wallrun, wallclimb, roll],
            fall_height,
            jump_buffer: self.jump_buffer,
            roll_window,
            dodging: self.dodging,
            springboard_approach: self.springboard.is_some(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::BoxWorld;

    fn ground() -> (Controller, BoxWorld) {
        let mut world = BoxWorld::default();
        world.add(Aabb::new(
            Vec3::new(-20.0, -1.0, -20.0),
            Vec3::new(20.0, 0.0, 20.0),
        ));
        let mut c = Controller::new(Tuning::default(), Vec3::ZERO, 0.0);
        c.state = State::Ground;
        (c, world)
    }

    #[test]
    fn slide_requires_forward_speed_and_matches_the_move() {
        let (mut c, world) = ground();
        let input = Input {
            crouch_pressed: true,
            crouch_held: true,
            ..Input::default()
        };
        c.vel = Vec3::X * 5.0;
        assert_eq!(
            c.diagnostics(&input, &world).checks[1].status,
            CheckStatus::Blocked
        );
        c.vel = c.forward() * (c.tuning.slide_min_speed + 0.5);
        assert_eq!(
            c.diagnostics(&input, &world).checks[1].status,
            CheckStatus::Ready
        );
        c.step(1.0 / 120.0, &input, &world);
        assert!(matches!(c.state, State::Slide { .. }));
        assert_eq!(
            c.diagnostics(&input, &world).checks[1].status,
            CheckStatus::Active
        );
    }

    #[test]
    fn jump_reports_coyote_expiry_and_low_ceiling() {
        let (mut c, mut world) = ground();
        c.state = State::Air;
        c.feet.y = 0.2;
        c.air_time = c.tuning.coyote_time * 0.5;
        assert_eq!(
            c.diagnostics(&Input::default(), &world).checks[0].status,
            CheckStatus::Ready
        );
        c.air_time = c.tuning.coyote_time;
        assert_eq!(
            c.diagnostics(&Input::default(), &world).checks[0].status,
            CheckStatus::Blocked
        );
        c.state = State::Ground;
        c.feet = Vec3::ZERO;
        c.crouched = true;
        world.add(Aabb::new(
            Vec3::new(-2.0, 1.3, -2.0),
            Vec3::new(2.0, 2.0, 2.0),
        ));
        assert!(
            c.diagnostics(&Input::default(), &world).checks[0]
                .reason
                .contains("Ceiling")
        );
    }

    #[test]
    fn climb_uses_the_actual_wall_probe_and_enters_the_move() {
        let (mut c, mut world) = ground();
        c.state = State::Air;
        c.feet = Vec3::new(0.0, 0.5, -3.65);
        c.vel = Vec3::new(0.0, 2.0, -4.0);
        c.jumped_since_ground = true;
        let input = Input {
            move_axis: Vec2::Y,
            ..Input::default()
        };
        assert_eq!(
            c.diagnostics(&input, &world).checks[4].status,
            CheckStatus::Blocked
        );
        world.add(Aabb::new(
            Vec3::new(-5.0, 0.0, -10.0),
            Vec3::new(5.0, 20.0, -4.0),
        ));
        assert_eq!(
            c.diagnostics(&input, &world).checks[4].status,
            CheckStatus::Ready
        );
        c.step(1.0 / 120.0, &input, &world);
        assert!(c.events.contains(&Event::WallClimbStart));
    }

    #[test]
    fn vault_requires_a_valid_landing_and_matches_the_move() {
        let (mut c, mut world) = ground();
        c.state = State::Air;
        c.feet.y = 0.1;
        c.vel = Vec3::new(0.0, 0.8, -4.0);
        c.jumped_since_ground = true;
        let input = Input {
            move_axis: Vec2::Y,
            ..Input::default()
        };
        assert_eq!(
            c.diagnostics(&input, &world).checks[2].status,
            CheckStatus::Blocked
        );
        world.add(Aabb::new(
            Vec3::new(-5.0, 0.0, -1.4),
            Vec3::new(5.0, 1.0, -1.2),
        ));
        assert_eq!(
            c.diagnostics(&input, &world).checks[2].status,
            CheckStatus::Ready
        );
        c.step(1.0 / 120.0, &input, &world);
        assert!(matches!(c.state, State::Vault(_)));
    }

    #[test]
    fn wallrun_checks_approach_and_dodge_lock_before_contact() {
        let (mut c, mut world) = ground();
        world.add(Aabb::new(
            Vec3::new(1.0, 0.0, -40.0),
            Vec3::new(1.5, 5.0, -3.0),
        ));
        c.state = State::Air;
        c.feet = Vec3::new(0.6, 0.5, -8.0);
        c.yaw = -25f32.to_radians();
        c.vel = c.forward() * 5.0 + Vec3::Y;
        c.jumped_since_ground = true;
        let input = Input {
            move_axis: Vec2::Y,
            ..Input::default()
        };
        c.dodging = true;
        assert!(
            c.diagnostics(&input, &world).checks[3]
                .reason
                .contains("Dodge")
        );
        c.dodging = false;
        assert_eq!(
            c.diagnostics(&input, &world).checks[3].status,
            CheckStatus::Ready
        );
        c.step(1.0 / 120.0, &input, &world);
        assert!(c.events.contains(&Event::WallRunStart));
    }

    #[test]
    fn roll_window_matches_landing_and_retrigger_delay() {
        let (mut c, world) = ground();
        c.state = State::Air;
        c.feet.y = 0.02;
        c.vel.y = -4.0;
        c.fall_peak = 3.0;
        c.roll_trigger_age = 0.3;
        assert!(
            c.diagnostics(&Input::default(), &world).checks[5]
                .reason
                .contains("retrigger")
        );
        c.roll_trigger_age = 0.05;
        assert_eq!(
            c.diagnostics(&Input::default(), &world).checks[5].status,
            CheckStatus::Ready
        );
        c.step(1.0 / 120.0, &Input::default(), &world);
        assert!(c.events.contains(&Event::Roll));
    }
}
