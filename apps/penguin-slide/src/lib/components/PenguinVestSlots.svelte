<script lang="ts">
  import { getContextSpine } from 'pixi-svelte';

  export let enabled = false;

  const spine = getContextSpine();

  const manageVestSlots = () => {
    if (!spine) return;
    const skeleton = spine.skeleton;
    if (!skeleton) return;

    try {
      const vestSlot = skeleton.findSlot('vest');
      if (vestSlot) {
        vestSlot.attachment = enabled ? vestSlot.data.attachment : null;
      }
    } catch (error) {
      console.error('PenguinVestSlots failed to update vest slot', error);
    }
  };

  $: manageVestSlots();
</script>
