//! Live, read-only parkour inspector. F3 toggles it; F4 holds the displayed
//! snapshot while gameplay continues. Input comes from the simulation, including pads.

use std::collections::VecDeque;

use bevy::prelude::*;
use bevy::window::PrimaryWindow;
use faith_move::controller::diagnostics::{CheckStatus, Diagnostics};
use faith_move::{Controller, Event, State};

use crate::Game;

const WIDTH: f32 = 356.0;
const INK: Color = Color::srgb(0.94, 0.96, 0.98);
const MUTED: Color = Color::srgb(0.66, 0.72, 0.78);
const ACCENT: Color = Color::srgb(1.0, 0.43, 0.32);
const READY: Color = Color::srgb(0.40, 0.91, 0.70);
const KEY_IDLE: Color = Color::srgba(0.70, 0.78, 0.88, 0.10);

#[derive(Resource)]
pub struct DebugHud {
    visible: bool,
    frozen: bool,
    refresh: f32,
    pulses: [f32; 4],
    history: VecDeque<String>,
    state: Option<&'static str>,
    map: Option<usize>,
}

impl Default for DebugHud {
    fn default() -> Self {
        Self {
            visible: true,
            frozen: false,
            refresh: 1.0,
            pulses: [0.0; 4],
            history: VecDeque::new(),
            state: None,
            map: None,
        }
    }
}

impl DebugHud {
    fn record(&mut self, time: f32, label: impl AsRef<str>) {
        self.history
            .push_front(format!("{time:6.1}s  {}", label.as_ref()));
        self.history.truncate(3);
    }
}

#[derive(Component)]
pub struct Panel;

#[derive(Component)]
pub enum Field {
    Mode,
    State,
    Explanation,
    Motion,
    Timing,
    Axes,
    Check(usize),
    History,
}

#[derive(Component)]
pub struct InputKey(usize);

#[derive(Component)]
pub struct SpeedBar;

fn label(value: impl Into<String>, size: f32, color: Color) -> impl Bundle {
    (
        Text::new(value),
        TextFont::from_font_size(size),
        TextColor(color),
    )
}

fn field(which: Field, size: f32) -> impl Bundle {
    let min_height = match which {
        Field::Explanation => px(48.0),
        Field::History => px(45.0),
        _ => Val::Auto,
    };
    (
        which,
        label("", size, INK),
        Node {
            flex_shrink: 0.0,
            min_height,
            ..default()
        },
    )
}

fn section(title: &'static str) -> impl Bundle {
    (
        label(title, 11.0, MUTED),
        Node {
            margin: UiRect::top(px(4.0)),
            ..default()
        },
    )
}

pub fn setup(mut commands: Commands) {
    commands.init_resource::<DebugHud>();
    commands
        .spawn((
            Panel,
            Node {
                position_type: PositionType::Absolute,
                top: px(16.0),
                right: px(16.0),
                width: px(WIDTH),
                padding: UiRect::all(px(16.0)),
                row_gap: px(7.0),
                flex_direction: FlexDirection::Column,
                border: UiRect::all(px(1.0)),
                border_radius: BorderRadius::all(px(10.0)),
                ..default()
            },
            BackgroundColor(Color::srgba(0.035, 0.045, 0.065, 0.94)),
            BorderColor::all(Color::srgba(0.65, 0.73, 0.84, 0.25)),
            UiTransform::default(),
            GlobalZIndex(20),
        ))
        .with_children(|panel| {
            panel.spawn(label("PARKOUR INSPECTOR", 17.0, ACCENT));
            panel.spawn(section("VIEW & WORLD HINTS  /  Esc to click"));
            for (i, title) in ["F5  Chase camera", "F6  Grabbable edges", "F7  Jump arc", "F8  Vault target"].into_iter().enumerate() {
                panel.spawn((
                    crate::parkour_debug::Toggle(i), Button,
                    Node { padding: UiRect::axes(px(8.0), px(4.0)), border_radius: BorderRadius::all(px(4.0)), flex_shrink: 0.0, ..default() },
                    BackgroundColor(KEY_IDLE),
                )).with_children(|button| {
                    button.spawn((crate::parkour_debug::ToggleLabel(i), label(title, 12.0, INK)));
                });
            }
            panel.spawn(label("Green: clear ledge candidate. Cyan: in grab range.\nYellow: ballistic guide. Orange: planned vault.", 11.0, MUTED));
            panel.spawn(field(Field::Mode, 11.0));
            panel.spawn(field(Field::State, 25.0));
            panel.spawn(field(Field::Explanation, 13.0));
            panel.spawn(field(Field::Motion, 15.0));
            panel
                .spawn((
                    Node {
                        width: percent(100.0),
                        height: px(4.0),
                        flex_shrink: 0.0,
                        ..default()
                    },
                    BackgroundColor(KEY_IDLE),
                ))
                .with_children(|track| {
                    track.spawn((
                        SpeedBar,
                        Node {
                            height: percent(100.0),
                            width: percent(0.0),
                            ..default()
                        },
                        BackgroundColor(ACCENT),
                    ));
                });
            panel.spawn(field(Field::Timing, 12.0));
            panel.spawn(section("INPUT  /  keyboard + controller"));
            for row in [["W", "A", "S", "D"], ["JUMP", "CROUCH", "TURN", "ATTACK"]]
                .into_iter()
                .enumerate()
            {
                panel
                    .spawn(Node {
                        column_gap: px(5.0),
                        ..default()
                    })
                    .with_children(|keys| {
                        for (column, name) in row.1.into_iter().enumerate() {
                            keys.spawn((
                                InputKey(row.0 * 4 + column),
                                Node {
                                    width: percent(25.0),
                                    height: px(25.0),
                                    align_items: AlignItems::Center,
                                    justify_content: JustifyContent::Center,
                                    border_radius: BorderRadius::all(px(4.0)),
                                    ..default()
                                },
                                BackgroundColor(KEY_IDLE),
                            ))
                            .with_children(|key| {
                                key.spawn(label(name, 11.0, INK));
                            });
                        }
                    });
            }
            panel.spawn(field(Field::Axes, 12.0));
            panel.spawn(section("ENTRY CHECKS  /  first unmet requirement"));
            for i in 0..6 {
                panel.spawn(field(Field::Check(i), 12.5));
            }
            panel.spawn(label(
                "Checks use this position; nearby fixtures can take priority.",
                11.0,
                MUTED,
            ));
            panel.spawn(section("RECENT MOVES"));
            panel.spawn(field(Field::History, 12.0));
            panel.spawn(label(
                "F3  hide panel      F4  freeze / resume readings",
                11.0,
                MUTED,
            ));
        });
}

fn explanation(c: &Controller, diagnostics: &Diagnostics) -> &'static str {
    if diagnostics.dodging {
        return "Sideways launch. Steering and wall catches unlock once the dodge descends.";
    }
    if diagnostics.springboard_approach {
        return "Committed to the two-step springboard. Run-in and launch are automatic.";
    }
    match c.state {
        State::Ground if c.crouched => {
            "Crouching reduces speed and body height. Release crouch where there is headroom."
        }
        State::Ground => {
            "Run straight to build sprint. Jump + full strafe selects a sideways dodge."
        }
        State::Air if c.vel.y > 0.0 => {
            "Rising. Hold forward near an obstacle to vault or catch a wall."
        }
        State::Air => {
            "Falling. A well-timed crouch press arms a landing roll; watch its window below."
        }
        State::Slide { .. } => {
            "Friction drains speed. Steer with look / strafe; release crouch to exit. Jump is ignored."
        }
        State::Roll { .. } => "The timed crouch press softened the landing and preserved momentum.",
        State::WallRun { .. } => {
            "Running along a wall. Jump kicks off; look away for a stronger outward push."
        }
        State::WallClimb { .. } => {
            "Upward momentum is draining. Q then jump kicks away; a reachable ledge is caught automatically."
        }
        State::WallClimbTurned { .. } => {
            "Turned away from the wall. Press jump to kick backward off it."
        }
        State::LedgeHang { .. } => {
            "Forward / jump pulls up, left / right shimmies, crouch drops. Turn then jump to kick off."
        }
        State::Vault(_)
        | State::Traverse(_)
        | State::StepUp { .. }
        | State::GrabTransfer { .. } => {
            "Following a planned path over the obstacle. Normal control resumes when the move finishes."
        }
        State::Balance { .. } => {
            "Counter the lean with left / right. Keep your view along the beam."
        }
        State::Swing { .. } => {
            "Hold forward to pump; jump on the forward swing. Crouch lets go, Q reverses direction."
        }
        State::ZipLine { .. } => {
            "Gravity accelerates the ride. Jump leaps off; crouch drops from the cable."
        }
        State::Stunned { .. } | State::SoftLand { .. } | State::Stumble { .. } => {
            "Recovering from an impact. Movement resumes when the recovery finishes."
        }
        State::LayOnGround { .. } => {
            "Landed on your back after an air turn. Jump / forward stands up; backward rolls into a crouch."
        }
        State::Barge { .. } | State::AirBarge { .. } => {
            "An attack at the door starts a barge or kick. The move carries you through it."
        }
        State::RumpSlide { .. } => {
            "The slope is too steep to stand on. Steer across it with left / right."
        }
        State::Vertigo { .. } => {
            "Stopped at a long drop. Movement input breaks the edge-look animation."
        }
        State::Climb { .. } | State::IntoClimb { .. } | State::ClimbExit { .. } => {
            "Ladder / pipe: forward climbs up, backward climbs down, crouch drops."
        }
        State::SwingJump { .. } => {
            "Travelling between swing bars; the next bar is caught automatically."
        }
        State::Takedown { .. } => {
            "Committed to a takedown. Movement and look are locked until it finishes."
        }
    }
}

fn event_label(event: Event) -> Option<String> {
    match event {
        Event::Jump => Some("Jump".into()),
        Event::Land { fall, impact } => Some(format!("Land: {fall:.1} m drop, {impact:.1} m/s")),
        Event::Dodge { .. } => Some("Sideways dodge".into()),
        Event::Turn180 => Some("180 turn".into()),
        Event::WallRunTurn => Some("Look out from wall".into()),
        Event::SlideEnd => Some("Slide ended".into()),
        Event::Death => Some("Respawn".into()),
        _ => crate::flash_label(event)
            .map(|name| name.split(" - ").next().unwrap_or(name).to_string()),
    }
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)] // Explicit Bevy resource/query access.
pub fn update(
    game: Res<Game>,
    menu: Res<crate::settings::Menu>,
    time: Res<Time<Real>>,
    keys: Res<ButtonInput<KeyCode>>,
    windows: Query<&Window, With<PrimaryWindow>>,
    mut hud: ResMut<DebugHud>,
    mut panel: Query<(&mut Visibility, &mut Node, &mut UiTransform, &ComputedNode), With<Panel>>,
    mut text: Query<(&Field, &mut Text, &mut TextColor)>,
    mut inputs: Query<(&InputKey, &mut BackgroundColor)>,
    mut bars: Query<&mut Node, (With<SpeedBar>, Without<Panel>)>,
    mut menu_root: Query<
        &mut Node,
        (
            With<crate::settings::MenuRoot>,
            Without<Panel>,
            Without<SpeedBar>,
        ),
    >,
) {
    if keys.just_pressed(KeyCode::F3) {
        hud.visible = !hud.visible;
        hud.refresh = 1.0;
    }
    if keys.just_pressed(KeyCode::F4) {
        hud.frozen = !hud.frozen;
        hud.refresh = 1.0;
    }
    for mut root in &mut menu_root {
        // Reserve the right side for the inspector so settings remain clickable.
        root.width = percent(if hud.visible { 60.0 } else { 100.0 });
    }
    if let Ok((mut visibility, mut node, mut transform, computed)) = panel.single_mut() {
        *visibility = if hud.visible {
            Visibility::Inherited
        } else {
            Visibility::Hidden
        };
        if let Ok(window) = windows.single() {
            // Scale around the centre, compensating the offset to keep the top/right
            // inset fixed. The whole panel fits smaller windows without clipped rows.
            let height = computed.size().y * computed.inverse_scale_factor();
            if height > 0.0 {
                let scale = ((window.height() - 32.0) / height)
                    .min((window.width() * 0.40) / WIDTH)
                    .clamp(0.1, 1.0);
                transform.scale = Vec2::splat(scale);
                node.top = px(16.0 - height * (1.0 - scale) * 0.5);
                node.right = px(16.0 - WIDTH * (1.0 - scale) * 0.5);
            }
        }
    }

    let c = &game.ctrl;
    let state_changed = hud.state != Some(c.state.name());
    if hud.map != Some(game.level_index) {
        hud.history.clear();
        hud.map = Some(game.level_index);
    }
    if game.debug_running {
        let now = time.elapsed_secs();
        let mut recorded = false;
        for &event in &c.events {
            if let Some(label) = event_label(event) {
                hud.record(now, label);
                recorded = true;
            }
        }
        if state_changed && !recorded {
            hud.record(now, c.state.name());
        }
    }
    hud.state = Some(c.state.name());

    // Only the mode label changes while frozen; the displayed inputs, history and
    // measurements remain one coherent snapshot. Gameplay keeps running normally.
    for (field, mut value, mut color) in &mut text {
        if matches!(field, Field::Mode) {
            value.0 = if hud.frozen {
                "FROZEN  /  F4 resumes readings"
            } else if menu.open {
                "PAUSED  /  Enter resumes gameplay"
            } else if !game.debug_running {
                "PAUSED  /  click the game to resume"
            } else {
                "LIVE  /  F4 freezes readings"
            }
            .into();
            color.0 = if hud.frozen { ACCENT } else { MUTED };
        }
    }
    if hud.frozen || !hud.visible {
        return;
    }
    let input = game.debug_input;
    for (i, pressed) in [
        input.jump_pressed,
        input.crouch_pressed,
        input.turn_pressed,
        input.melee_pressed,
    ]
    .into_iter()
    .enumerate()
    {
        hud.pulses[i] = if pressed {
            0.18
        } else {
            (hud.pulses[i] - time.delta_secs()).max(0.0)
        };
    }
    let lit = [
        input.move_axis.y > 0.05,
        input.move_axis.x < -0.05,
        input.move_axis.y < -0.05,
        input.move_axis.x > 0.05,
        input.jump_held || hud.pulses[0] > 0.0,
        input.crouch_held || hud.pulses[1] > 0.0,
        hud.pulses[2] > 0.0,
        hud.pulses[3] > 0.0,
    ];
    for (key, mut background) in &mut inputs {
        background.0 = if lit[key.0] {
            Color::srgb(0.72, 0.22, 0.14)
        } else {
            KEY_IDLE
        };
    }
    hud.refresh += time.delta_secs();
    if hud.refresh < 0.1 && !state_changed {
        return;
    }
    hud.refresh = 0.0;
    let diagnostics = c.diagnostics(&input, &game.world);
    for (field, mut value, mut color) in &mut text {
        value.0 = match *field {
            Field::Mode => continue,
            Field::State => if diagnostics.dodging {
                "Dodge"
            } else if diagnostics.springboard_approach {
                "Springboard approach"
            } else {
                c.state.name()
            }
            .into(),
            Field::Explanation => explanation(c, &diagnostics).into(),
            Field::Motion => format!(
                "Speed {:.2} m/s  |  Up {:+.2} m/s\nForward  {:.2} m/s     Sprint  {:.0}%",
                c.horizontal_speed(),
                c.vel.y,
                c.vel.dot(c.forward()),
                c.sprint_charge * 100.0
            ),
            Field::Timing => format!(
                "Fall  {:.2} m     {}\nJump buffer  {:.0} ms     Roll window  {:.0} ms",
                diagnostics.fall_height,
                if c.is_coiled() {
                    "COILED"
                } else if c.crouched {
                    "CROUCHED"
                } else {
                    "STANDING HEIGHT"
                },
                diagnostics.jump_buffer * 1000.0,
                diagnostics.roll_window * 1000.0
            ),
            Field::Axes => format!(
                "Forward {:+.2}    Strafe {:+.2}",
                input.move_axis.y, input.move_axis.x
            ),
            Field::Check(i) => {
                let check = &diagnostics.checks[i];
                let status = match check.status {
                    CheckStatus::Active => {
                        color.0 = ACCENT;
                        "ACTIVE"
                    }
                    CheckStatus::Ready => {
                        color.0 = READY;
                        "PASS"
                    }
                    CheckStatus::Blocked => {
                        color.0 = MUTED;
                        "WAIT"
                    }
                };
                format!("{}  [{}]\n{}", check.name, status, check.reason)
            }
            Field::History => {
                if hud.history.is_empty() {
                    "Move to see state changes here.".into()
                } else {
                    hud.history.iter().cloned().collect::<Vec<_>>().join("\n")
                }
            }
        };
    }
    for mut bar in &mut bars {
        bar.width = percent(c.sprint_charge.clamp(0.0, 1.0) * 100.0);
    }
}
