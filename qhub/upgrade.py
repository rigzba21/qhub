import logging
from abc import ABC
import pathlib
import re
import json
import string
import secrets

from packaging.version import parse as ver_parse

from pydantic.error_wrappers import ValidationError

from .schema import verify
from .utils import backup_config_file, load_yaml, yaml
from .version import __version__

logger = logging.getLogger(__name__)


def do_upgrade(config_filename, attempt_fixes=False):

    config = load_yaml(config_filename)

    try:
        verify(config)
        print(
            f"Your config file {config_filename} appears to be already up-to-date for qhub version {__version__}"
        )
        return
    except (ValidationError, ValueError) as e:
        if config.get("qhub_version", "") == __version__:
            # There is an unrelated validation problem
            print(
                f"Your config file {config_filename} appears to be already up-to-date for qhub version {__version__} but there is another validation error.\n"
            )
            raise e

    start_version = config.get("qhub_version", "")

    UpgradeStep.upgrade(
        config, start_version, __version__, config_filename, attempt_fixes
    )

    # Backup old file
    backup_config_file(config_filename, f".{start_version or 'old'}")

    with config_filename.open("wt") as f:
        yaml.dump(config, f)

    print(
        f"Saving new config file {config_filename} ready for QHub version {__version__}"
    )

    ci_cd = config.get("ci_cd", {}).get("type", "")
    if ci_cd in ("github-actions", "gitlab-ci"):
        print(
            f"\nSince you are using ci_cd {ci_cd} you also need to re-render the workflows and re-commit the files to your Git repo:\n"
            f"   qhub render -c {config_filename}\n"
        )


class UpgradeStep(ABC):
    _steps = {}

    version = ""  # Each subclass must have a version

    def __init_subclass__(cls):
        assert cls.version != ""
        assert (
            cls.version not in cls._steps
        )  # Would mean multiple upgrades for the same step
        cls._steps[cls.version] = cls

    @classmethod
    def has_step(cls, version):
        return version in cls._steps

    @classmethod
    def upgrade(
        cls, config, start_version, finish_version, config_filename, attempt_fixes=False
    ):
        """
        Runs through all required upgrade steps (i.e. relevant subclasses of UpgradeStep).
        Calls UpgradeStep.upgrade_step for each.
        """
        starting_ver = ver_parse(start_version)
        finish_ver = ver_parse(finish_version)
        step_versions = sorted(
            [
                v
                for v in cls._steps.keys()
                if ver_parse(v) > starting_ver and ver_parse(v) <= finish_ver
            ],
            key=ver_parse,
        )

        current_start_version = start_version
        for stepcls in [cls._steps[str(v)] for v in step_versions]:
            step = stepcls()
            config = step.upgrade_step(
                config,
                current_start_version,
                config_filename,
                attempt_fixes=attempt_fixes,
            )
            current_start_version = step.get_version()
            print("\n")

        return config

    def get_version(self):
        return self.version

    def requires_qhub_version_field(self):
        return ver_parse(self.version) > ver_parse("0.3.13")

    def upgrade_step(self, config, start_version, config_filename, *args, **kwargs):
        """
        Perform the upgrade from start_version to self.version

        Generally, this will be in-place in config, but must also return config dict.

        config_filename may be useful to understand the file path for qhub-config.yaml, for example
        to output another file in the same location.

        The standard body here will take care of setting qhub_version and also updating the image tags.

        It should normally be left as-is for all upgrades. Use _version_specific_upgrade below
        for any actions that are only required for the particular upgrade you are creating.
        """

        finish_version = self.get_version()

        print(
            f"\n---> Starting upgrade from {start_version or 'old version'} to {finish_version}\n"
        )

        # Set the new version
        if start_version == "":
            assert "qhub_version" not in config
        assert self.version != start_version

        if self.requires_qhub_version_field():
            print(f"Setting qhub_version to {self.version}")
            config["qhub_version"] = self.version

        # Update images
        start_version_regex = start_version.replace(".", "\\.")
        if start_version == "":
            print("Looking for any previous image version")
            start_version_regex = "0\\.[0-3]\\.[0-9]{1,2}"
        docker_image_regex = re.compile(
            f"^([A-Za-z0-9_-]+/[A-Za-z0-9_-]+):v{start_version_regex}$"
        )

        def _new_docker_image(
            v,
        ):
            m = docker_image_regex.match(v)
            if m:
                return ":".join([m.groups()[0], f"v{finish_version}"])
            return None

        for k, v in config.get("default_images", {}).items():
            newimage = _new_docker_image(v)
            if newimage:
                print(f"In default_images: {k}: upgrading {v} to {newimage}")
                config["default_images"][k] = newimage

        for i, v in enumerate(config.get("profiles", {}).get("jupyterlab", [])):
            oldimage = v.get("kubespawner_override", {}).get("image", "")
            newimage = _new_docker_image(oldimage)
            if newimage:
                print(
                    f"In profiles: jupyterlab: [{i}]: upgrading {oldimage} to {newimage}"
                )
                config["profiles"]["jupyterlab"][i]["kubespawner_override"][
                    "image"
                ] = newimage

        for k, v in config.get("profiles", {}).get("dask_worker", {}).items():
            oldimage = v.get("image", "")
            newimage = _new_docker_image(oldimage)
            if newimage:
                print(
                    f"In profiles: dask_worker: {k}: upgrading {oldimage} to {newimage}"
                )
                config["profiles"]["dask_worker"][k]["image"] = newimage

        # Run any version-specific tasks
        return self._version_specific_upgrade(
            config, start_version, config_filename, *args, **kwargs
        )

    def _version_specific_upgrade(
        self, config, start_version, config_filename, *args, **kwargs
    ):
        """
        Override this method in subclasses if you need to do anything specific to your version
        """
        return config


class Upgrade_0_3_12(UpgradeStep):
    version = "0.3.12"

    def _version_specific_upgrade(
        self, config, start_version, config_filename, *args, **kwargs
    ):
        """
        This verison of QHub requires a conda_store image for the first time.
        """
        if config.get("default_images", {}).get("conda_store", None) is None:
            newimage = f"quansight/qhub-conda-store:v{self.version}"
            print(f"Adding default_images: conda_store image as {newimage}")
            config["default_images"]["conda_store"] = newimage
        return config


class Upgrade_0_3_14(UpgradeStep):
    version = "0.3.14"

    def _version_specific_upgrade(
        self, config, start_version, config_filename: pathlib.Path, *args, **kwargs
    ):
        """
        Upgrade to Keycloak.
        """
        security = config.get("security", {})
        users = security.get("users", {})
        groups = security.get("groups", {})

        # Custom Authenticators are no longer allowed
        if (
            config.get("security", {}).get("authentication", {}).get("type", "")
            == "custom"
        ):
            customauth_warning = (
                f"Custom Authenticators are no longer supported in {self.version} because Keycloak "
                "manages all authentication.\nYou need to find a way to support your authentication "
                "requirements within Keycloak."
            )
            if not kwargs.get("attempt_fixes", False):
                raise ValueError(
                    f"{customauth_warning}\n\nRun `qhub upgrade --attempt-fixes` to switch to basic Keycloak authentication instead."
                )
            else:
                print(f"\nWARNING: {customauth_warning}")
                print(
                    "\nSwitching to basic Keycloak authentication instead since you specified --attempt-fixes."
                )
                config["security"]["authentication"] = {"type": "password"}

        # Create a group/user import file for Keycloak

        realm_import_filename = config_filename.parent / "qhub-users-import.json"

        realm = {"id": "qhub", "realm": "qhub"}
        realm["users"] = [
            {
                "username": k,
                "enabled": True,
                "groups": sorted(
                    list(
                        (
                            {v.get("primary_group", "")}
                            | set(v.get("secondary_groups", []))
                        )
                        - {""}
                    )
                ),
            }
            for k, v in users.items()
        ]
        realm["groups"] = [
            {"name": k, "path": f"/{k}"}
            for k, v in groups.items()
            if k not in {"users", "admin"}
        ]

        backup_config_file(realm_import_filename)

        with realm_import_filename.open("wt") as f:
            json.dump(realm, f, indent=2)

        print(
            f"\nSaving user/group import file {realm_import_filename}.\n\n"
            "ACTION REQUIRED: You must import this file into the Keycloak admin webpage after you redeploy QHub.\n"
            "Visit the URL path /auth/ and login as 'root'. Under Manage, click Import and select this file.\n"
        )

        if "users" in security:
            del security["users"]
        if "groups" in security:
            del security["groups"]

        # Create root password
        default_password = "".join(
            secrets.choice(string.ascii_letters + string.digits) for i in range(16)
        )
        security.setdefault("keycloak", {})["initial_root_password"] = default_password

        print(
            f"Generated default random password={default_password} for Keycloak root user (Please change at /auth/ URL path).\n"
        )

        # project was never needed in Azure - it remained as PLACEHOLDER in earlier qhub inits!
        if "azure" in config:
            if "project" in config["azure"]:
                del config["azure"]["project"]

        return config


# Manually-added upgrade steps must go above this line
if not UpgradeStep.has_step(__version__):
    # Always have a way to upgrade to the latest version number, even if no customizations
    class UpgradeLatest(UpgradeStep):
        version = __version__