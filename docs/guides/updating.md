# Updating

Updates arrive as a new image. On Unraid they show as **update ready** on the Docker tab like any other
container's.

## Tags

The `docker` workflow publishes two tags for each release (`.github/workflows/docker.yml`):

- `ghcr.io/kernelpanic-studios/dropwatch:<version>`, for example `:0.3.0`, which never changes;
- `:latest`, which moves to every new release.

To stay on a version, use the version tag in **Repository** (Unraid) or `docker run`. Images are published
only after the tests pass. Releases come from version tags; the workflow can also be started by hand, and a
manual run publishes under the branch name and moves `:latest` too (finding F3 in
[the architecture findings](../architecture/README.md#findings)).

## What happens on start

1. If this build has not opened the database before, Dropwatch copies `drops.db` to
   `drops.db.before-<version>+<build>` and keeps the newest two copies. If the copy fails (a full disk), a
   warning is logged and it starts anyway.
2. The database gets any new tables and columns. Old rows keep working; details they never recorded show
   as unknown.
3. Mining resumes on the saved Twitch session. No sign-in is needed.
4. A browser tab left open from before shows **Dropwatch was updated** with **Reload**.

**Settings › About** shows the version and build running.

## Rolling back

1. Stop the container.
2. In the data folder, copy `drops.db.before-<the version you are going back to>+...` over `drops.db`.
   Changes made since the upgrade (claims, settings) are lost.
3. Run the older image by its version tag.

Running an older image on a newer database without the copy usually works, because changes are only
additions, but it is not tested.

## When Twitch changes something

Mining can stop or stop earning until Dropwatch is updated. The **Mining isn't earning** and **Mining
stopped on an error** notifications are there so you find out; the fix arrives as a new image.

## Known limitations

- No automatic updates: Unraid or a tool like Watchtower pulls the image.
- `linux/amd64` only.
