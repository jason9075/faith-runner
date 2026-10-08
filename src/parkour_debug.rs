//! Camera inspection and opt-in world hints. Candidate ledges validate free
//! hang/pull-up space; cyan additionally satisfies the current grab probe.
use bevy::prelude::*;
use bevy::ui::FocusPolicy;
use faith_move::world::{WithDoors, find_ledge, probe_wall};
use faith_move::{Body, State, World};

use crate::{Game, PlayerCamera, viewmodel::ViewmodelCamera};

#[derive(Resource, Default)]
pub struct Options {
    pub chase: bool,
    pub edges: bool,
    pub arc: bool,
    pub vault: bool,
    markers: Vec<(Vec3, String, Color)>,
}

#[derive(Component)]
pub struct Toggle(pub usize);
#[derive(Component)]
pub struct ToggleLabel(pub usize);
#[derive(Component)]
pub struct Marker(usize);
#[derive(Component)]
pub struct Runner;

pub fn setup(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    // A neutral collision-body proxy remains useful without a game installation.
    commands.spawn((
        Runner,
        Mesh3d(meshes.add(Capsule3d::new(0.30, 1.20))),
        MeshMaterial3d(materials.add(Color::srgb(0.9, 0.20, 0.08))),
        Transform::default(),
        Visibility::Hidden,
    ));
    for i in 0..12 {
        commands.spawn((
            Marker(i),
            Text::new(""),
            TextFont::from_font_size(12.0),
            TextColor(Color::WHITE),
            Node {
                position_type: PositionType::Absolute,
                padding: UiRect::all(px(3.0)),
                ..default()
            },
            BackgroundColor(Color::srgba(0.02, 0.03, 0.05, 0.85)),
            FocusPolicy::Pass,
            GlobalZIndex(2),
            Visibility::Hidden,
        ));
    }
}

fn enabled(options: &Options, index: usize) -> bool {
    match index {
        0 => options.chase,
        1 => options.edges,
        2 => options.arc,
        _ => options.vault,
    }
}

fn toggle(options: &mut Options, index: usize) {
    let value = match index {
        0 => &mut options.chase,
        1 => &mut options.edges,
        2 => &mut options.arc,
        _ => &mut options.vault,
    };
    *value = !*value;
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)] // Explicit Bevy query access.
pub fn camera(
    game: Res<Game>,
    keys: Res<ButtonInput<KeyCode>>,
    mut options: ResMut<Options>,
    buttons: Query<(&Toggle, &Interaction), Changed<Interaction>>,
    mut captions: Query<(&ToggleLabel, &mut Text)>,
    mut main: Query<&mut Transform, (With<PlayerCamera>, Without<Runner>)>,
    mut vm: Query<&mut Camera, With<ViewmodelCamera>>,
    mut runner: Query<(&mut Transform, &mut Visibility), (With<Runner>, Without<PlayerCamera>)>,
    me: Option<Res<crate::me_viewmodel::MeArms>>,
) {
    for (i, key) in [KeyCode::F5, KeyCode::F6, KeyCode::F7, KeyCode::F8]
        .into_iter()
        .enumerate()
    {
        if keys.just_pressed(key) {
            toggle(&mut options, i);
        }
    }
    for (button, interaction) in &buttons {
        if *interaction == Interaction::Pressed {
            toggle(&mut options, button.0);
        }
    }
    for (label, mut text) in &mut captions {
        let name = [
            "F5 Chase camera",
            "F6 Grabbable edges",
            "F7 Jump arc",
            "F8 Vault target",
        ][label.0];
        text.0 = format!(
            "[{}] {name}",
            if enabled(&options, label.0) {
                "ON"
            } else {
                "OFF"
            }
        );
    }
    for mut cam in &mut vm {
        cam.is_active = !options.chase;
    }
    let c = &game.ctrl;
    if let Ok((mut transform, mut visibility)) = runner.single_mut() {
        // Render the actual changing collision height, including slides and coils.
        *visibility = if options.chase && !me.as_ref().is_some_and(|m| m.active) {
            Visibility::Inherited
        } else {
            Visibility::Hidden
        };
        transform.translation = c.feet + Vec3::Y * c.height() * 0.5;
        transform.scale = Vec3::new(1.0, c.height() / 1.8, 1.0);
    }
    if options.chase {
        let target = c.feet + Vec3::Y * (c.height() * 0.75);
        let rotation = Quat::from_euler(EulerRot::YXZ, c.yaw, c.pitch.clamp(-0.8, 0.8), 0.0);
        let offset = rotation * Vec3::new(0.0, 1.2, 4.0);
        let closed = game
            .world
            .fixtures
            .iter()
            .enumerate()
            .filter_map(|(i, f)| match f {
                faith_move::Fixture::Door { b, .. }
                    if c.doors_open.get(i).copied().unwrap_or(0.0) == 0.0 =>
                {
                    Some(*b)
                }
                _ => None,
            })
            .collect();
        let world = WithDoors {
            world: &game.world,
            closed,
        };
        let fraction = world
            .sweep(Vec3::splat(0.15), target, offset)
            .map(|hit| (hit.t - 0.04).max(0.0))
            .unwrap_or(1.0);
        if let Ok(mut transform) = main.single_mut() {
            let position = target + offset * fraction;
            *transform = Transform::from_translation(position)
                .looking_at(target + c.forward() * 0.5, Vec3::Y);
        }
    }
}

pub fn draw(game: Res<Game>, mut options: ResMut<Options>, mut gizmos: Gizmos) {
    options.markers.clear();
    let c = &game.ctrl;
    let tu = &c.tuning;
    let closed = game
        .world
        .fixtures
        .iter()
        .enumerate()
        .filter_map(|(i, f)| match f {
            faith_move::Fixture::Door { b, .. }
                if c.doors_open.get(i).copied().unwrap_or(0.0) == 0.0 =>
            {
                Some(*b)
            }
            _ => None,
        })
        .collect();
    let world = &WithDoors {
        world: &game.world,
        closed,
    };
    let green = Color::srgb(0.3, 1.0, 0.5);
    let cyan = Color::srgb(0.1, 0.9, 1.0);
    let yellow = Color::srgb(1.0, 0.85, 0.2);
    let orange = Color::srgb(1.0, 0.4, 0.1);

    if options.chase {
        gizmos.line(
            c.feet + Vec3::Y * c.height(),
            c.feet + Vec3::Y * c.height() + c.forward() * 0.8,
            orange,
        );
    }
    if options.edges {
        let mut boxes: Vec<_> = game
            .world
            .boxes
            .iter()
            .filter(|b| {
                let nearest = c.feet.clamp(b.min, b.max);
                nearest.distance(c.feet) < 12.0 && b.size().y > 0.1
            })
            .collect();
        boxes.sort_by(|a, b| {
            a.center()
                .distance_squared(c.feet)
                .total_cmp(&b.center().distance_squared(c.feet))
        });
        for b in boxes.into_iter().take(12) {
            let y = b.max.y;
            let faces = [
                (
                    Vec3::NEG_Z,
                    Vec3::new(b.min.x, y, b.min.z),
                    Vec3::new(b.max.x, y, b.min.z),
                ),
                (
                    Vec3::Z,
                    Vec3::new(b.min.x, y, b.max.z),
                    Vec3::new(b.max.x, y, b.max.z),
                ),
                (
                    Vec3::NEG_X,
                    Vec3::new(b.min.x, y, b.min.z),
                    Vec3::new(b.min.x, y, b.max.z),
                ),
                (
                    Vec3::X,
                    Vec3::new(b.max.x, y, b.min.z),
                    Vec3::new(b.max.x, y, b.max.z),
                ),
            ];
            for (normal, a, z) in faces {
                let steps = (a.distance(z) / 0.8).ceil().clamp(1.0, 16.0) as usize;
                let mut labelled = false;
                for i in 0..steps {
                    let p = a.lerp(z, (i as f32 + 0.5) / steps as f32);
                    if p.distance(c.feet) > 12.0 {
                        continue;
                    }
                    let body = Body {
                        half_width: tu.half_width,
                        height: tu.stand_height,
                    };
                    let feet = p + normal * (body.reach_toward(normal) + 0.03)
                        - Vec3::Y * tu.hang_hands_above_feet;
                    if world.overlaps(&body.aabb(feet)) {
                        continue;
                    }
                    if find_ledge(
                        world,
                        body,
                        feet,
                        normal,
                        tu.hang_hands_above_feet - 0.03,
                        tu.hang_hands_above_feet + 0.03,
                        tu.crouch_height,
                    )
                    .is_none()
                    {
                        continue;
                    }
                    let lift = if c.is_coiled() { tu.coil_lift } else { 0.0 };
                    let reachable = c.state == State::Air
                        && c.vel.y < 2.5
                        && c.forward().dot(-normal) > 0.5
                        && probe_wall(
                            world,
                            c.body(),
                            c.feet,
                            c.forward(),
                            0.35,
                            0.2,
                            c.height() - 0.1,
                        )
                        .is_some_and(|(n, _)| n.dot(normal) > 0.9)
                        && find_ledge(
                            world,
                            c.body(),
                            c.feet,
                            normal,
                            tu.mantle_hi - lift,
                            tu.hang_hands_above_feet + tu.ledge_grab_hi_extra - lift,
                            tu.crouch_height,
                        )
                        .is_some_and(|top| (top - y).abs() < 0.05);
                    let color = if reachable { cyan } else { green };
                    let tangent = (z - a).normalize_or_zero();
                    let half = (a.distance(z) / steps as f32) * 0.45;
                    gizmos.line(
                        p - tangent * half + normal * 0.02 + Vec3::Y * 0.02,
                        p + tangent * half + normal * 0.02 + Vec3::Y * 0.02,
                        color,
                    );
                    if !labelled && options.markers.len() < 8 {
                        options.markers.push((
                            p + Vec3::Y * 0.15,
                            if reachable {
                                "EDGE: in grab range"
                            } else {
                                "EDGE: clear hang space"
                            }
                            .into(),
                            color,
                        ));
                        labelled = true;
                    }
                }
            }
        }
    }
    if options.arc {
        // A ballistic guide, deliberately not a full controller prediction: no
        // steering, dodge, wall transitions, vaulting or root-motion adjustments.
        let mut position = c.feet;
        let mut velocity = c.vel;
        if c.state == State::Ground {
            velocity.y = tu.jump_speed;
            if velocity.dot(c.forward()) > 0.1 {
                velocity += c.forward() * tu.jump_add_forward;
            }
        }
        if matches!(c.state, State::Ground | State::Air) {
            let body = c.body();
            for _ in 0..90 {
                let dt = 1.0 / 60.0;
                velocity.y -= tu.gravity * dt;
                let delta = velocity * dt;
                let centre = position + Vec3::Y * body.height * 0.5;
                if let Some(hit) = world.sweep(
                    Vec3::new(body.half_width, body.height * 0.5, body.half_width),
                    centre,
                    delta,
                ) {
                    let end = position + delta * hit.t;
                    gizmos.line(position + Vec3::Y * 0.05, end + Vec3::Y * 0.05, yellow);
                    gizmos.line(end - Vec3::X * 0.25, end + Vec3::X * 0.25, yellow);
                    gizmos.line(end - Vec3::Z * 0.25, end + Vec3::Z * 0.25, yellow);
                    options.markers.push((
                        end + Vec3::Y * 0.2,
                        "JUMP: first contact (guide)".into(),
                        yellow,
                    ));
                    break;
                }
                gizmos.line(
                    position + Vec3::Y * 0.05,
                    position + delta + Vec3::Y * 0.05,
                    yellow,
                );
                position += delta;
            }
        }
    }
    if options.vault {
        let plan = match c.state {
            State::Vault(v) => Some(v),
            State::Air => {
                let fwd = c.forward();
                faith_move::vault::plan(
                    world,
                    tu,
                    c.body(),
                    c.feet,
                    c.vel,
                    fwd,
                    fwd * c.pitch.cos() + Vec3::Y * c.pitch.sin(),
                )
            }
            _ => None,
        };
        if let Some(v) = plan {
            gizmos.linestrip([v.from, v.hand, v.over, v.end], orange);
            gizmos.line(v.end - Vec3::X * 0.3, v.end + Vec3::X * 0.3, orange);
            gizmos.line(v.end - Vec3::Z * 0.3, v.end + Vec3::Z * 0.3, orange);
            options.markers.push((
                v.end + Vec3::Y * 0.2,
                format!("VAULT: {}", v.anim()),
                orange,
            ));
        }
    }
}

pub fn labels(
    options: Res<Options>,
    camera: Query<(&Camera, &GlobalTransform), With<PlayerCamera>>,
    mut labels: Query<(
        &Marker,
        &mut Node,
        &mut Text,
        &mut TextColor,
        &mut Visibility,
    )>,
) {
    let Ok((camera, transform)) = camera.single() else {
        return;
    };
    for (marker, mut node, mut text, mut color, mut visibility) in &mut labels {
        *visibility = Visibility::Hidden;
        if let Some((point, caption, ink)) = options.markers.get(marker.0)
            && let Ok(screen) = camera.world_to_viewport(transform, *point)
            && let Some(size) = camera.logical_viewport_size()
            && screen.x >= 0.0
            && screen.y >= 0.0
            && screen.x < size.x - 160.0
            && screen.y < size.y - 30.0
        {
            node.left = px(screen.x);
            node.top = px(screen.y);
            text.0 = caption.clone();
            color.0 = *ink;
            *visibility = Visibility::Inherited;
        }
    }
}
