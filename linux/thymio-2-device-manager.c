/*
    This file is part of tdm-launcher.
    Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
    Miniature Mobile Robots group, Switzerland
    Author: Yves Piguet
*/

#include <signal.h>

#include <gtk/gtk.h>
#include <gio/gio.h>

#ifndef APP_VERSION
#define APP_VERSION "1.0.0"
#endif

#ifndef APP_BUILD
#define APP_BUILD "1"
#endif

typedef struct {
    GtkApplication *app;
    GtkStatusIcon *status_icon;
    GtkWidget *menu;
    GtkWidget *about_dialog;
    GSubprocess *process;
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

static void update_icon(AppState *state, gboolean running)
{
    GdkPixbuf *pixbuf = create_icon(running);

    gtk_status_icon_set_from_pixbuf(state->status_icon, pixbuf);
    gtk_status_icon_set_tooltip_text(
        state->status_icon,
        running ? "Thymio Device Manager" : "Thymio Device Manager (not running)"
    );

    g_object_unref(pixbuf);
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
    state->quitting = TRUE;

    if (state->process != NULL) {
        g_subprocess_send_signal(state->process, SIGTERM);
        g_timeout_add(500, force_exit_timeout, state);
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

static void popup_menu(AppState *state, guint button, guint activate_time)
{
    gtk_menu_popup(
        GTK_MENU(state->menu),
        NULL,
        NULL,
        gtk_status_icon_position_menu,
        state->status_icon,
        button,
        activate_time
    );
}

static void on_status_icon_popup_menu(
    GtkStatusIcon *status_icon,
    guint button,
    guint activate_time,
    gpointer user_data
)
{
    AppState *state = user_data;
    (void) status_icon;

    popup_menu(state, button, activate_time);
}

static void on_status_icon_activate(GtkStatusIcon *status_icon, gpointer user_data)
{
    AppState *state = user_data;
    (void) status_icon;

    popup_menu(state, 0, gtk_get_current_event_time());
}

static void on_process_exit(GObject *source_object, GAsyncResult *result, gpointer user_data)
{
    AppState *state = user_data;
    GSubprocess *process = G_SUBPROCESS(source_object);

    g_subprocess_wait_finish(process, result, NULL);

    if (state->process == process) {
        g_clear_object(&state->process);
        update_icon(state, FALSE);
    }

    if (state->quitting) {
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
        update_icon(state, FALSE);
        g_clear_error(&error);
        g_free(tdm_path);
        return;
    }

    update_icon(state, TRUE);
    g_subprocess_wait_async(state->process, NULL, on_process_exit, state);
    g_free(tdm_path);
}

static void on_shutdown(GApplication *app, gpointer user_data)
{
    AppState *state = user_data;
    (void) app;

    if (state->process != NULL) {
        g_subprocess_send_signal(state->process, SIGTERM);
        g_subprocess_force_exit(state->process);
        g_clear_object(&state->process);
    }

    if (state->status_icon != NULL) {
        gtk_status_icon_set_visible(state->status_icon, FALSE);
        g_clear_object(&state->status_icon);
    }

    if (state->about_dialog != NULL) {
        gtk_widget_destroy(state->about_dialog);
    }

    if (state->menu != NULL) {
        gtk_widget_destroy(state->menu);
        state->menu = NULL;
    }
}

static void on_activate(GApplication *app, gpointer user_data)
{
    AppState *state = user_data;
    GtkWidget *about_item;
    GtkWidget *separator;
    GtkWidget *quit_item;

    if (state->status_icon != NULL) {
        return;
    }

    g_application_hold(app);
    state->held = TRUE;

    state->menu = gtk_menu_new();
    about_item = gtk_menu_item_new_with_label("About");
    g_signal_connect(about_item, "activate", G_CALLBACK(on_menu_about), state);
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), about_item);
    separator = gtk_separator_menu_item_new();
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), separator);
    quit_item = gtk_menu_item_new_with_label("Quit Thymio Device Manager");
    g_signal_connect(quit_item, "activate", G_CALLBACK(on_menu_quit), state);
    gtk_menu_shell_append(GTK_MENU_SHELL(state->menu), quit_item);
    gtk_widget_show_all(state->menu);

    state->status_icon = gtk_status_icon_new();
    gtk_status_icon_set_visible(state->status_icon, TRUE);
    g_signal_connect(state->status_icon, "popup-menu", G_CALLBACK(on_status_icon_popup_menu), state);
    g_signal_connect(state->status_icon, "activate", G_CALLBACK(on_status_icon_activate), state);

    update_icon(state, FALSE);
    launch_tdm(state);
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
