// Read-only observer. Never offers focus, input, activation, or window mutation.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'org.worldline.GnomeObserver';
const OBJECT_PATH = '/org/worldline/GnomeObserver';
const INTERFACE = 'org.worldline.GnomeObserver1';
const DBUS_XML = `<node>
  <interface name="${INTERFACE}">
    <method name="GetSnapshot">
      <arg name="snapshot" type="s" direction="out"/>
    </method>
  </interface>
</node>`;

function read(getter, fallback = null) {
    try {
        const value = getter();
        return value === undefined ? fallback : value;
    } catch (_) {
        return fallback;
    }
}

function ref(window) {
    if (!window)
        return null;
    const sequence = read(() => window.get_stable_sequence());
    return sequence === null ? null : String(sequence);
}

function rect(window) {
    const r = read(() => window.get_frame_rect());
    return r ? {x: r.x, y: r.y, width: r.width, height: r.height} : null;
}

function record(actor, index, stackIndices) {
    const window = actor.meta_window;
    const parent = read(() => window.get_transient_for());
    const title = read(() => window.get_title());
    const workspace = read(() => window.get_workspace());
    return {
        id: ref(window),
        gtk_app_id: read(() => window.get_gtk_application_id()),
        wm_class: read(() => window.get_wm_class()),
        wm_class_instance: read(() => window.get_wm_class_instance()),
        title: typeof title === 'string' ? title.slice(0, 512) : null,
        title_truncated: typeof title === 'string' && title.length > 512,
        reported_pid: read(() => window.get_pid()),
        transient_for: ref(parent), // Native Meta.Window link, not inferred affiliation.
        frame: rect(window),
        monitor: read(() => window.get_monitor()),
        workspace: read(() => workspace.index()),
        minimized: Boolean(window.minimized),
        showing_on_workspace: read(() => window.showing_on_its_workspace()),
        focused: read(() => window.has_focus()),
        fullscreen: read(() => window.is_fullscreen()),
        above: read(() => window.is_above()),
        window_type: read(() => window.get_window_type()),
        actor_present: true, // This record originated from actor.meta_window.
        actor_visible: read(() => actor.visible),
        enumeration_index: index,
        stack_index: stackIndices?.get(window) ?? null,
    };
}

export default class WindowObserver extends Extension {
    enable() {
        this._generation = GLib.uuid_string_random();
        this._exported = Gio.DBusExportedObject.wrapJSObject(DBUS_XML, this);
        this._exported.export(Gio.DBus.session, OBJECT_PATH);
        this._busOwner = Gio.bus_own_name_on_connection(
            Gio.DBus.session, BUS_NAME, Gio.BusNameOwnerFlags.NONE, null, null);
    }

    disable() {
        if (this._busOwner !== undefined) {
            Gio.bus_unown_name(this._busOwner);
            this._busOwner = undefined;
        }
        if (this._exported) {
            this._exported.unexport();
            this._exported = null;
        }
    }

    GetSnapshot() {
        const actors = read(() => global.get_window_actors(), [])
            .filter(actor => Boolean(actor?.meta_window));
        const windows = actors.map(actor => actor.meta_window);
        // The native stack sort is optional; enumeration order alone does not
        // prove which window is above another.
        const stack = read(() => global.display.sort_windows_by_stacking([...windows]));
        const stackIndices = Array.isArray(stack) && stack.length === windows.length
            ? new Map(stack.map((window, index) => [window, index]))
            : null;
        const limit = 256;
        const observed = actors.slice(0, limit)
            .map((actor, index) => record(actor, index, stackIndices))
            .filter(window => window.id !== null);
        return JSON.stringify({
            schema: 1,
            generation: this._generation,
            observed_at: GLib.get_real_time() / 1_000_000,
            order_source: stackIndices ? 'meta-display-stacking' : 'actor-enumeration',
            total_windows: actors.length,
            truncated: actors.length > limit,
            windows: observed,
        });
    }
}
