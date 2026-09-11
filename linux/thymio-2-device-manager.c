/*
    This file is part of tdm-launcher.
    Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
    Miniature Mobile Robots group, Switzerland
    Author: Yves Piguet
*/

#include <signal.h>

#include <gtk/gtk.h>
#include <gio/gio.h>
#include <glib/gstdio.h>
#include <libayatana-appindicator/app-indicator.h>

#ifndef APP_VERSION
#define APP_VERSION "1.0.0"
#endif

#ifndef APP_BUILD
#define APP_BUILD "1"
#endif

typedef struct {
    GtkApplication *app;
    AppIndicator *indicator;
    GtkWidget *menu;
    GtkWidget *window;
    GtkWidget *status_label;
    GtkWidget *tray_label;
    GtkWidget *about_dialog;
    GSubprocess *process;
    gchar *icon_dir;
    gchar *running_icon;
    gchar *stopped_icon;
    guint quit_timeout;
    gboolean tray_connected;
    gboolean held;
    gboolean quitting;
} AppState;

static GdkPixbuf *create_icon(gboolean running)
{
    const int size = 32;
    cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, size, size);
    cairo_t *cr = cairo_create(surface);
    GdkPixbuf *pixbuf;

    cairo_scale(cr, size / 20.0, size / 20.0);

    cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.55);
    cairo_move_to(cr, 3.0, 3.0);
    cairo_line_to(cr, 17.0, 3.0);
    cairo_line_to(cr, 17.0, 13.0);
    cairo_curve_to(cr, 13.0, 17.0, 7.0, 17.0, 3.0, 13.0);
    cairo_close_path(cr);
    cairo_set_line_width(cr, 1.6);
    cairo_stroke_preserve(cr);

    cairo_set_source_rgba(cr, 0.14, 0.14, 0.14, 0.95);
    cairo_fill(cr);

    if (!running) {
        cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR);
        cairo_move_to(cr, 8.0, 7.0);
        cairo_line_to(cr, 12.0, 11.0);
        cairo_move_to(cr, 8.0, 11.0);
        cairo_line_to(cr, 12.0, 7.0);
        cairo_set_line_width(cr, 2.2);
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_stroke(cr);

        cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.75);
        cairo_move_to(cr, 8.0, 7.0);
        cairo_line_to(cr, 12.0, 11.0);
        cairo_move_to(cr, 8.0, 11.0);
        cairo_line_to(cr, 12.0, 7.0);
        cairo_set_line_width(cr, 0.6);
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        cairo_stroke(cr);
    }

    pixbuf = gdk_pixbuf_get_from_surface(surface, 0, 0, size, size);

    cairo_destroy(cr);
    cairo_surface_destroy(surface);

    return pixbuf;
}

static void prepare_icons(AppState *state)
{
    GError *error = NULL;
    state->icon_dir = g_dir_make_tmp("thymio-device-manager-XXXXXX", &error);
    if (state->icon_dir == NULL) {
        g_warning("Cannot create tray icons: %s", error->message);
        g_clear_error(&error);
        return;
    }

    for (int running = 0; running <= 1; running++) {
        GdkPixbuf *pixbuf = create_icon(running);
        gchar *path = g_build_filename(state->icon_dir,
            running ? "thymio-running.png" : "thymio-stopped.png", NULL);
        if (!gdk_pixbuf_save(pixbuf, path, "png", &error, NULL)) {
            g_warning("Cannot save tray icon: %s", error->message);
            g_clear_error(&error);
            g_unlink(path);
            g_clear_pointer(&path, g_free);
        }
        if (running) {
            state->running_icon = path;
        } else {
            state->stopped_icon = path;
        }
        g_object_unref(pixbuf);
    }
}

static void update_status(AppState *state, gboolean running, const gchar *message)
{
    const gchar *icon = running ? state->running_icon : state->stopped_icon;
    app_indicator_set_icon_full(state->indicator,
        icon != NULL ? icon : (running ? "applications-education" : "dialog-error"),
        running ? "Thymio Device Manager" : "Thymio Device Manager (not running)");
    gtk_label_set_text(GTK_LABEL(state->status_label), message);
}

static gchar *get_tdm_path(void)
{
    gchar *launcher_path = g_file_read_link("/proc/self/exe", NULL);
    gchar *launcher_dir;
    gchar *tdm_path;

    if (launcher_path == NULL) {
        launcher_dir = g_get_current_dir();
    } else {
        launcher_dir = g_path_get_dirname(launcher_path);
        g_free(launcher_path);
    }

    tdm_path = g_build_filename(launcher_dir, "thymio-device-manager", NULL);
    g_free(launcher_dir);

    return tdm_path;
}

static gboolean force_exit_timeout(gpointer user_data)
{
    AppState *state = user_data;

    state->quit_timeout = 0;
    if (state->process != NULL) {
        g_subprocess_force_exit(state->process);
    }

    return G_SOURCE_REMOVE;
}

static void release_application(AppState *state)
{
    if (state->held) {
        g_application_release(G_APPLICATION(state->app));
        state->held = FALSE;
    }
}

static void request_quit(AppState *state)
{
    if (state->quitting) {
        return;
    }
    state->quitting = TRUE;

    if (state->process != NULL) {
        g_subprocess_send_signal(state->process, SIGTERM);
        state->quit_timeout = g_timeout_add(500, force_exit_timeout, state);
        return;
    }

    release_application(state);
    g_application_quit(G_APPLICATION(state->app));
}

static void on_menu_quit(GtkMenuItem *menu_item, gpointer user_data)
{
    AppState *state = user_data;
    (void) menu_item;

    request_quit(state);
}

static void on_about_dialog_destroy(GtkWidget *dialog, gpointer user_data)
{
    AppState *state = user_data;

    if (state->about_dialog == dialog) {
        state->about_dialog = NULL;
    }
}

static void on_about_dialog_response(
    GtkDialog *dialog,
    gint response_id,
    gpointer user_data
)
{
    (void) response_id;
    (void) user_data;

    gtk_widget_destroy(GTK_WIDGET(dialog));
}

static void on_menu_about(GtkMenuItem *menu_item, gpointer user_data)
{
    AppState *state = user_data;
    GtkWidget *dialog;
    GdkPixbuf *logo;
    gchar *version;
    (void) menu_item;

    if (state->about_dialog != NULL) {
        gtk_window_present(GTK_WINDOW(state->about_dialog));
        return;
    }

    dialog = gtk_about_dialog_new();
    state->about_dialog = dialog;

    version = APP_BUILD[0] == '\0'
        ? g_strdup(APP_VERSION)
        : g_strdup_printf("%s (%s)", APP_VERSION, APP_BUILD);
    logo = create_icon(TRUE);

    gtk_window_set_application(GTK_WINDOW(dialog), state->app);
    gtk_window_set_transient_for(GTK_WINDOW(dialog), GTK_WINDOW(state->window));
    gtk_about_dialog_set_program_name(
        GTK_ABOUT_DIALOG(dialog),
        "Thymio 2 Device Manager"
    );
    gtk_about_dialog_set_version(GTK_ABOUT_DIALOG(dialog), version);
    gtk_about_dialog_set_copyright(
        GTK_ABOUT_DIALOG(dialog),
        "Copyright 2026, Mobsya and École Polytechnique Fédérale de Lausanne (EPFL)."
    );
    gtk_about_dialog_set_logo(GTK_ABOUT_DIALOG(dialog), logo);

    g_free(version);
    g_object_unref(logo);

    g_signal_connect(dialog, "response", G_CALLBACK(on_about_dialog_response), state);
    g_signal_connect(dialog, "destroy", G_CALLBACK(on_about_dialog_destroy), state);
    gtk_window_present(GTK_WINDOW(dialog));
}

static void show_status(AppState *state)
{
    if (!state->quitting) {
        gtk_window_present(GTK_WINDOW(state->window));
    }
}

static void on_menu_status(GtkMenuItem *menu_item, gpointer user_data)
{
    (void) menu_item;
    show_status(user_data);
}

static gboolean on_window_delete(GtkWidget *window, GdkEvent *event, gpointer user_data)
{
    AppState *state = user_data;
    (void) event;

    if (state->tray_connected) {
        gtk_widget_hide(window);
    } else {
        request_quit(state);
    }
    return TRUE;
}

static void on_indicator_connection_changed(
    AppIndicator *indicator, gboolean connected, gpointer user_data)
{
    AppState *state = user_data;
    (void) indicator;

    state->tray_connected = connected;
    gtk_label_set_text(GTK_LABEL(state->tray_label), connected
        ? "Closing this window keeps the device manager in the tray.\nUse Quit to stop it."
        : "No tray is available. Keep this window open while using Thymio.\nClosing it stops the device manager.");
    if (!connected) {
        show_status(state);
    }
}

static void create_status_window(AppState *state)
{
    GtkWidget *box;
    GtkWidget *buttons;
    GtkWidget *about_button;
    GtkWidget *quit_button;
    GdkPixbuf *icon = create_icon(TRUE);

    state->window = gtk_application_window_new(state->app);
    gtk_window_set_title(GTK_WINDOW(state->window), "Thymio 2 Device Manager");
    gtk_window_set_default_size(GTK_WINDOW(state->window), 420, -1);
    gtk_window_set_icon(GTK_WINDOW(state->window), icon);
    g_object_unref(icon);
    g_signal_connect(state->window, "delete-event", G_CALLBACK(on_window_delete), state);

    box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 16);
    gtk_container_set_border_width(GTK_CONTAINER(box), 24);
    gtk_container_add(GTK_CONTAINER(state->window), box);
    state->status_label = gtk_label_new("Starting Thymio Device Manager…");
    gtk_label_set_line_wrap(GTK_LABEL(state->status_label), TRUE);
    gtk_label_set_max_width_chars(GTK_LABEL(state->status_label), 60);
    gtk_label_set_selectable(GTK_LABEL(state->status_label), TRUE);
    gtk_box_pack_start(GTK_BOX(box), state->status_label, TRUE, TRUE, 0);
    state->tray_label = gtk_label_new(NULL);
    gtk_label_set_line_wrap(GTK_LABEL(state->tray_label), TRUE);
    gtk_box_pack_start(GTK_BOX(box), state->tray_label, FALSE, FALSE, 0);

    buttons = gtk_button_box_new(GTK_ORIENTATION_HORIZONTAL);
    gtk_button_box_set_layout(GTK_BUTTON_BOX(buttons), GTK_BUTTONBOX_END);
    gtk_box_set_spacing(GTK_BOX(buttons), 8);
    about_button = gtk_button_new_with_label("About");
    g_signal_connect(about_button, "clicked", G_CALLBACK(on_menu_about), state);
    gtk_container_add(GTK_CONTAINER(buttons), about_button);
    quit_button = gtk_button_new_with_label("Quit");
    g_signal_connect(quit_button, "clicked", G_CALLBACK(on_menu_quit), state);
    gtk_container_add(GTK_CONTAINER(buttons), quit_button);
    gtk_box_pack_start(GTK_BOX(box), buttons, FALSE, FALSE, 0);
    gtk_widget_show_all(box);
    on_indicator_connection_changed(NULL, FALSE, state);
}

static void on_process_exit(GObject *source_object, GAsyncResult *result, gpointer user_data)
{
    AppState *state = user_data;
    GSubprocess *process = G_SUBPROCESS(source_object);
    GError *error = NULL;
    gchar *message;

    if (!g_subprocess_wait_finish(process, result, &error)) {
        message = g_strdup_printf("Could not monitor Thymio Device Manager: %s", error->message);
        g_clear_error(&error);
    } else if (g_subprocess_get_if_signaled(process)) {
        message = g_strdup_printf("Thymio Device Manager stopped (signal %d).",
            g_subprocess_get_term_sig(process));
    } else {
        message = g_strdup_printf("Thymio Device Manager stopped (exit status %d).",
            g_subprocess_get_exit_status(process));
    }

    if (state->process == process) {
        g_clear_object(&state->process);
        update_status(state, FALSE, message);
        if (!state->quitting) {
            g_printerr("%s\n", message);
            show_status(state);
        }
    }
    g_free(message);

    if (state->quitting) {
        if (state->quit_timeout != 0) {
            g_source_remove(state->quit_timeout);
            state->quit_timeout = 0;
        }
        release_application(state);
        g_application_quit(G_APPLICATION(state->app));
    }
}

static void launch_tdm(AppState *state)
{
    gchar *tdm_path = get_tdm_path();
    const gchar *argv[] = {tdm_path, NULL};
    GError *error = NULL;

    state->process = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_NONE, &error);
    if (state->process == NULL) {
        gchar *message = g_strdup_printf("Could not start Thymio Device Manager:\n%s", error->message);
        update_status(state, FALSE, message);
        g_printerr("%s\n", message);
        g_free(message);
        show_status(state);
        g_clear_error(&error);
        g_free(tdm_path);
        return;
    }

    update_status(state, TRUE, "Thymio Device Manager is running.");
    g_subprocess_wait_async(state->process, NULL, on_process_exit, state);
    g_free(tdm_path);
}

static void on_shutdown(GApplication *app, gpointer user_data)
{
    AppState *state = user_data;
    (void) app;

    state->quitting = TRUE;
    if (state->quit_timeout != 0) {
        g_source_remove(state->quit_timeout);
        state->quit_timeout = 0;
    }
    if (state->process != NULL) {
        g_subprocess_send_signal(state->process, SIGTERM);
        g_subprocess_force_exit(state->process);
        g_clear_object(&state->process);
    }

    if (state->indicator != NULL) {
        g_signal_handlers_disconnect_by_data(state->indicator, state);
        app_indicator_set_status(state->indicator, APP_INDICATOR_STATUS_PASSIVE);
        g_clear_object(&state->indicator);
    }

    if (state->about_dialog != NULL) {
        gtk_widget_destroy(state->about_dialog);
    }

    if (state->menu != NULL) {
        gtk_widget_destroy(state->menu);
        g_clear_object(&state->menu);
    }
    if (state->window != NULL) {
        gtk_widget_destroy(state->window);
        state->window = NULL;
    }
    if (state->running_icon != NULL) {
        g_unlink(state->running_icon);
        g_clear_pointer(&state->running_icon, g_free);
    }
    if (state->stopped_icon != NULL) {
        g_unlink(state->stopped_icon);
        g_clear_pointer(&state->stopped_icon, g_free);
    }
    if (state->icon_dir != NULL) {
        g_rmdir(state->icon_dir);
        g_clear_pointer(&state->icon_dir, g_free);
    }
}

static void on_activate(GApplication *app, gpointer user_data)
{
    AppState *state = user_data;
    GtkWidget *status_item;
    GtkWidget *about_item;
    GtkWidget *separator;
    GtkWidget *quit_item;

    if (state->held) {
        show_status(state);
        return;
    }

    g_application_hold(app);
    state->held = TRUE;

    create_status_window(state);
    state->menu = gtk_menu_new();
    g_object_ref_sink(state->menu);
    status_item = gtk_menu_item_new_with_label("Show Status");
    g_signal_connect(status_item, "activate", G_CALLBACK(on_menu_status), state);
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), status_item);
    about_item = gtk_menu_item_new_with_label("About");
    g_signal_connect(about_item, "activate", G_CALLBACK(on_menu_about), state);
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), about_item);
    separator = gtk_separator_menu_item_new();
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), separator);
    quit_item = gtk_menu_item_new_with_label("Quit Thymio Device Manager");
    g_signal_connect(quit_item, "activate", G_CALLBACK(on_menu_quit), state);
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), quit_item);
    gtk_widget_show_all(state->menu);

    prepare_icons(state);
    state->indicator = app_indicator_new("thymio-2-device-manager",
        "applications-education", APP_INDICATOR_CATEGORY_APPLICATION_STATUS);
    app_indicator_set_title(state->indicator, "Thymio 2 Device Manager");
    app_indicator_set_menu(state->indicator, GTK_MENU(state->menu));
    g_signal_connect(state->indicator, "connection-changed",
        G_CALLBACK(on_indicator_connection_changed), state);
    app_indicator_set_status(state->indicator, APP_INDICATOR_STATUS_ACTIVE);

    launch_tdm(state);
    show_status(state);
}

int main(int argc, char **argv)
{
    AppState state = {0};
    int status;

    state.app = gtk_application_new("org.mobsya.thymio-2-device-manager", G_APPLICATION_DEFAULT_FLAGS);
    g_signal_connect(state.app, "activate", G_CALLBACK(on_activate), &state);
    g_signal_connect(state.app, "shutdown", G_CALLBACK(on_shutdown), &state);

    status = g_application_run(G_APPLICATION(state.app), argc, argv);
    g_object_unref(state.app);

    return status;
}
